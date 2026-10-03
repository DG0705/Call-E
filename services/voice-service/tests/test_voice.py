"""Tests for the voice service application logic."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import httpx
import pytest

from voice_service.agent_runtime import (
    AgentConfiguration,
    AgentRuntimeHttpClient,
    RuntimeResult,
)
from voice_service.audio import (
    AudioChunk,
    audio_content_type,
    decode_wav,
    encode_wav,
)
from voice_service.config import STTSettings, TTSSettings, load_stt_settings, load_tts_settings
from voice_service.factory import (
    STTProviderFactory,
    TTSProviderFactory,
    VoiceProviderConfigurationError,
)
from voice_service.models import (
    VOICE_SESSIONS_COLLECTION,
    VoiceSession,
)
from voice_service.session import VoiceSessionManager
from voice_service.session_store import (
    VOICE_SESSION_LOOKUP_INDEX,
    InMemoryVoiceSessionStore,
    MongoVoiceSessionStore,
)
from voice_service.stt import MockSTTProvider, STTResult
from voice_service.tts import MockTTSProvider, TTSResult

from call_e_shared.exceptions import PlatformError


class FakeAgentRuntimeClient:
    """Deterministic runtime boundary used by the session manager tests."""

    def __init__(
        self,
        *,
        available: bool = True,
        respond_error: Exception | None = None,
        agent: AgentConfiguration | None = None,
    ) -> None:
        self.available = available
        self.respond_error = respond_error
        self.agent = agent or AgentConfiguration(
            id="agent-1", tenant_id="tenant-1", language="en", voice_id="neutral-voice"
        )
        self.get_calls: list[tuple[str, str]] = []
        self.respond_calls: list[dict[str, str]] = []

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration:
        self.get_calls.append((tenant_id, agent_id))
        if not self.available:
            raise RuntimeError("agent unavailable")
        return self.agent

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        self.respond_calls.append(
            {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "message": message,
            }
        )
        if self.respond_error is not None:
            raise self.respond_error
        return RuntimeResult(
            text=f"Reply to: {message}",
            provider_name="mock",
            model_name="mock-agent-runtime-v1",
            conversation_id=conversation_id,
            agent_id=agent_id,
        )


class FailingSTTProvider:
    async def transcribe(self, audio: AudioChunk) -> STTResult:
        raise RuntimeError("stt failed")


class EmptyTranscriptSTTProvider:
    async def transcribe(self, audio: AudioChunk) -> STTResult:
        return STTResult(text="", provider="mock-empty")


class FailingTTSProvider:
    async def synthesize(self, **kwargs: object) -> TTSResult:
        raise RuntimeError("tts failed")

    def synthesize_stream(self, **kwargs: object) -> AsyncIterator[AudioChunk]:
        raise RuntimeError("tts failed")


class FailingAgentRuntime:
    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration:
        raise RuntimeError("unavailable")

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        raise RuntimeError("unavailable")


class FakeVoiceSessionCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []
        self.indexes: list[tuple[list[tuple[str, int]], dict[str, object]]] = []
        self.filters: list[dict[str, str]] = []

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: object) -> str:
        self.indexes.append((keys, kwargs))
        return str(kwargs["name"])

    async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
        self.filters.append(filter)
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ),
            None,
        )

    async def insert_one(self, document: dict[str, object]) -> None:
        if any(existing.get("_id") == document.get("_id") for existing in self.documents):
            raise ValueError("duplicate session id")
        self.documents.append(dict(document))

    async def update_one(
        self, filter: dict[str, str], update: dict[str, object], **kwargs: object
    ) -> None:
        document = await self.find_one(filter)
        if document is not None:
            document.update(update["$set"])  # type: ignore[arg-type]


class FakeVoiceSessionDatabase:
    def __init__(self) -> None:
        self.sessions = FakeVoiceSessionCollection()

    def __getitem__(self, name: str) -> FakeVoiceSessionCollection:
        assert name == VOICE_SESSIONS_COLLECTION
        return self.sessions


class FakeAgentCollection:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ),
            None,
        )


class FakeCoreDatabase:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.agents = FakeAgentCollection(documents)

    async def list_collection_names(self, **kwargs: object) -> list[str]:
        return ["agents"]

    def __getitem__(self, name: str) -> FakeAgentCollection:
        assert name == "agents"
        return self.agents


def agent_document() -> dict[str, object]:
    return {
        "_id": "agent-1",
        "tenant_id": "tenant-1",
        "name": "Receptionist",
        "role": "customer support assistant",
        "system_prompt": "Help customers clearly.",
        "personality": "warm and concise",
        "language": "en",
        "voice_id": "neutral-voice",
        "goals": [],
        "allowed_tools": [],
        "knowledge_sources": [],
        "created_at": "2026-08-03T12:00:00Z",
        "updated_at": "2026-08-03T12:00:00Z",
    }


def build_manager(
    *,
    runtime: object | None = None,
    stt: object | None = None,
    tts: object | None = None,
    store: object | None = None,
) -> VoiceSessionManager:
    return VoiceSessionManager(
        stt_provider=stt or MockSTTProvider(),
        tts_provider=tts or MockTTSProvider(),
        agent_runtime=runtime or FakeAgentRuntimeClient(),  # type: ignore[arg-type]
        session_store=store or InMemoryVoiceSessionStore(),  # type: ignore[arg-type]
    )


def test_voice_session_model_roundtrips_mongo_id() -> None:
    session = VoiceSession.model_validate(
        {
            "_id": "session-1",
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
            "status": "active",
            "created_at": "2026-08-10T12:00:00Z",
            "updated_at": "2026-08-10T12:00:00Z",
        }
    )

    assert session.session_id == "session-1"
    assert session.status == "active"
    assert session.model_dump()["session_id"] == "session-1"
    assert session.model_dump(by_alias=True)["_id"] == "session-1"


def test_audio_content_type_mapping() -> None:
    assert audio_content_type("pcm") == "audio/pcm"
    assert audio_content_type("wav") == "audio/wav"
    assert audio_content_type("ulaw") == "audio/basic"


def test_wav_encode_decode_roundtrip() -> None:
    chunk = AudioChunk(data=b"pcm-audio-bytes", format="pcm")
    wav = encode_wav(chunk)

    assert wav.format == "wav"
    assert wav.data.startswith(b"RIFF")
    decoded = decode_wav(wav)

    assert decoded.format == "pcm"
    assert decoded.data == chunk.data
    assert decoded.sample_rate == chunk.sample_rate
    assert decoded.channels == chunk.channels


def test_wav_helpers_reject_invalid_audio() -> None:
    wav_chunk = AudioChunk(data=b"pcm-audio-bytes", format="wav")
    with pytest.raises(ValueError):
        encode_wav(wav_chunk)
    with pytest.raises(ValueError):
        decode_wav(AudioChunk(data=b"not-a-wav", format="wav"))
    with pytest.raises(ValueError):
        decode_wav(AudioChunk(data=b"RIFF", format="wav"))


def test_mock_stt_provider_returns_deterministic_transcript() -> None:
    provider = MockSTTProvider()
    audio = AudioChunk(data=b"audio-bytes", format="pcm")

    result = asyncio.run(provider.transcribe(audio))

    assert result.text == "Mock transcription of customer audio."
    assert result.provider == "mock"
    assert result.confidence == 0.95
    assert provider.last_audio is audio
    assert provider.calls == 1


def test_mock_tts_provider_synthesizes_encodings() -> None:
    provider = MockTTSProvider()

    pcm = asyncio.run(provider.synthesize(text="Hello", output_format="pcm"))
    wav = asyncio.run(provider.synthesize(text="Hello", output_format="wav"))

    assert pcm.audio.data == b"Hello"
    assert pcm.audio.format == "pcm"
    assert pcm.content_type == "audio/pcm"
    assert wav.audio.format == "wav"
    assert wav.content_type == "audio/wav"
    assert decode_wav(wav.audio).data == b"Hello"
    assert provider.last_text == "Hello"


def test_provider_factories_select_mock_and_reject_unknown() -> None:
    stt = STTProviderFactory.create(STTSettings(provider="mock"))
    tts = TTSProviderFactory.create(TTSSettings(provider="mock"))

    assert isinstance(stt, MockSTTProvider)
    assert isinstance(tts, MockTTSProvider)
    with pytest.raises(VoiceProviderConfigurationError):
        STTProviderFactory.create(STTSettings(provider="watson"))
    with pytest.raises(VoiceProviderConfigurationError):
        TTSProviderFactory.create(TTSSettings(provider="azure"))


def test_provider_factories_fail_fast_without_credentials() -> None:
    with pytest.raises(VoiceProviderConfigurationError, match="DEEPGRAM_API_KEY"):
        STTProviderFactory.create(
            STTSettings(provider="deepgram", deepgram_api_key=None)
        )
    with pytest.raises(VoiceProviderConfigurationError, match="ELEVENLABS_API_KEY"):
        TTSProviderFactory.create(
            TTSSettings(provider="elevenlabs", elevenlabs_api_key=None)
        )


def test_provider_factories_select_real_providers_with_credentials() -> None:
    from voice_service.stt_providers import DeepgramSTTProvider
    from voice_service.tts_providers import ElevenLabsTTSProvider

    stt = STTProviderFactory.create(
        STTSettings(provider="deepgram", deepgram_api_key="test-key")
    )
    tts = TTSProviderFactory.create(
        TTSSettings(provider="elevenlabs", elevenlabs_api_key="test-key")
    )

    assert isinstance(stt, DeepgramSTTProvider)
    assert isinstance(tts, ElevenLabsTTSProvider)


def test_settings_default_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOICE_STT_PROVIDER", raising=False)
    monkeypatch.delenv("VOICE_TTS_PROVIDER", raising=False)

    assert load_stt_settings().provider == "mock"
    assert load_tts_settings().provider == "mock"


def test_mongo_session_store_indexes_create_get_save() -> None:
    database = FakeVoiceSessionDatabase()
    store = MongoVoiceSessionStore(database)
    session = VoiceSession.model_validate(
        {
            "_id": "session-1",
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
            "status": "created",
            "created_at": "2026-08-10T12:00:00Z",
            "updated_at": "2026-08-10T12:00:00Z",
        }
    )

    asyncio.run(store.ensure_indexes())
    asyncio.run(store.create(session))
    session.status = "active"
    asyncio.run(store.save(session))
    loaded = asyncio.run(
        store.get(tenant_id="tenant-1", session_id="session-1")
    )

    assert database.sessions.indexes == [
        ([("tenant_id", 1), ("_id", 1)], {"name": VOICE_SESSION_LOOKUP_INDEX, "unique": True})
    ]
    assert loaded is not None
    assert loaded.status == "active"
    assert database.sessions.documents[0]["_id"] == "session-1"


def test_mongo_session_store_isolates_tenants() -> None:
    database = FakeVoiceSessionDatabase()
    store = MongoVoiceSessionStore(database)
    session = VoiceSession.model_validate(
        {
            "_id": "session-1",
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
            "status": "created",
            "created_at": "2026-08-10T12:00:00Z",
            "updated_at": "2026-08-10T12:00:00Z",
        }
    )
    asyncio.run(store.create(session))

    other_tenant = asyncio.run(
        store.get(tenant_id="tenant-2", session_id="session-1")
    )

    assert other_tenant is None
    assert database.sessions.filters[-1] == {"_id": "session-1", "tenant_id": "tenant-2"}


def test_manager_creates_session_with_agent_voice() -> None:
    runtime = FakeAgentRuntimeClient()
    store = InMemoryVoiceSessionStore()
    manager = build_manager(runtime=runtime, store=store)

    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    assert session.status == "created"
    assert session.voice_id == "neutral-voice"
    assert session.language == "en"
    assert runtime.get_calls == [("tenant-1", "agent-1")]
    assert (
        asyncio.run(store.get(tenant_id="tenant-1", session_id=session.session_id))
        is not None
    )


def test_manager_creation_fails_when_agent_unavailable() -> None:
    manager = build_manager(runtime=FailingAgentRuntime())

    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            manager.create_session(
                tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
            )
        )

    assert excinfo.value.code == "voice_agent_unavailable"
    assert excinfo.value.status_code == 502


def test_manager_processes_full_turn_pipeline() -> None:
    runtime = FakeAgentRuntimeClient()
    stt = MockSTTProvider()
    tts = MockTTSProvider()
    manager = build_manager(runtime=runtime, stt=stt, tts=tts)

    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"customer-audio", format="pcm"),
        )
    )

    assert result.transcript == "Mock transcription of customer audio."
    assert result.response_text == "Reply to: Mock transcription of customer audio."
    assert result.audio.data == result.response_text.encode()
    assert result.content_type == "audio/pcm"
    assert result.stt_provider == "mock"
    assert result.tts_provider == "mock"
    assert runtime.respond_calls == [
        {
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
            "message": "Mock transcription of customer audio.",
        }
    ]
    assert stt.last_audio is not None
    assert stt.last_audio.format == "pcm"
    assert (
        asyncio.run(
            manager.get_session(tenant_id="tenant-1", session_id=session.session_id)
        ).status
        == "active"
    )


def test_manager_decodes_wav_input_before_stt() -> None:
    stt = MockSTTProvider()
    manager = build_manager(stt=stt)
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    wav = encode_wav(AudioChunk(data=b"wav-payload", format="pcm"))

    asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1", session_id=session.session_id, audio=wav
        )
    )

    assert stt.last_audio is not None
    assert stt.last_audio.format == "pcm"
    assert stt.last_audio.data == b"wav-payload"


def test_manager_rejects_empty_and_unsupported_audio() -> None:
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    with pytest.raises(PlatformError) as empty:
        asyncio.run(
            manager.process_audio_input(
                tenant_id="tenant-1",
                session_id=session.session_id,
                audio=AudioChunk(data=b"", format="pcm"),
            )
        )
    assert empty.value.code == "empty_audio"
    assert empty.value.status_code == 400

    with pytest.raises(PlatformError) as unsupported:
        asyncio.run(
            manager.process_audio_input(
                tenant_id="tenant-1",
                session_id=session.session_id,
                audio=AudioChunk.model_construct(data=b"x", format="mp3"),
            )
        )
    assert unsupported.value.code == "unsupported_audio_format"
    assert unsupported.value.status_code == 400


def test_manager_rejects_malformed_wav() -> None:
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            manager.process_audio_input(
                tenant_id="tenant-1",
                session_id=session.session_id,
                audio=AudioChunk(data=b"broken-wav", format="wav"),
            )
        )

    assert excinfo.value.code == "invalid_audio_format"
    assert excinfo.value.status_code == 400


def test_manager_returns_422_when_no_speech_recognized() -> None:
    manager = build_manager(stt=EmptyTranscriptSTTProvider())
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            manager.process_audio_input(
                tenant_id="tenant-1",
                session_id=session.session_id,
                audio=AudioChunk(data=b"audio", format="pcm"),
            )
        )

    assert excinfo.value.code == "stt_no_transcript"
    assert excinfo.value.status_code == 422
    assert (
        asyncio.run(
            manager.get_session(tenant_id="tenant-1", session_id=session.session_id)
        ).status
        == "active"
    )


@pytest.mark.parametrize(
    ("stage", "manager", "code", "fallback_fragment"),
    [
        (
            "stt",
            build_manager(stt=FailingSTTProvider()),
            "voice_stt_error",
            "repeat your request",
        ),
        (
            "runtime",
            build_manager(runtime=FakeAgentRuntimeClient(respond_error=RuntimeError("boom"))),
            "voice_runtime_error",
            "reaching our systems",
        ),
    ],
)
def test_manager_returns_spoken_fallback_when_recoverable_stage_fails(
    stage: str,
    manager: VoiceSessionManager,
    code: str,
    fallback_fragment: str,
) -> None:
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    assert fallback_fragment in result.response_text
    assert result.audio.data
    assert result.runtime_provider == "fallback"
    current = asyncio.run(
        manager.get_session(tenant_id="tenant-1", session_id=session.session_id)
    )
    assert current.status == "active"


def test_manager_keeps_session_active_when_tts_fails() -> None:
    manager = build_manager(tts=FailingTTSProvider())
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    # A dead TTS provider must not fail the session or the call: the turn
    # returns empty audio and the next turn is still accepted.
    assert result.audio.data == b""
    current = asyncio.run(
        manager.get_session(tenant_id="tenant-1", session_id=session.session_id)
    )
    assert current.status == "active"

    second = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )
    assert second.audio.data == b""
    assert second.transcript


def test_failed_turn_recovers_on_next_successful_turn() -> None:
    attempts = 0

    class FlakyOnceTTSProvider(MockTTSProvider):
        async def synthesize(self, **kwargs: object) -> TTSResult:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("tts down once")
            return await super().synthesize(**kwargs)

    manager = build_manager(tts=FlakyOnceTTSProvider())
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    async def main() -> tuple[object, object]:
        first = await manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
        second = await manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
        return first, second

    first, second = asyncio.run(main())

    assert "trouble reaching our systems" in first.response_text
    assert first.audio.data != b""
    assert second.audio.data != b""


def test_manager_rejects_turn_after_session_ended() -> None:
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    asyncio.run(
        manager.end_session(tenant_id="tenant-1", session_id=session.session_id)
    )

    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            manager.process_audio_input(
                tenant_id="tenant-1",
                session_id=session.session_id,
                audio=AudioChunk(data=b"audio", format="pcm"),
            )
        )
    assert excinfo.value.code == "voice_session_ended"
    assert excinfo.value.status_code == 409


def test_manager_end_session_is_idempotent_per_status() -> None:
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    ended = asyncio.run(
        manager.end_session(tenant_id="tenant-1", session_id=session.session_id)
    )
    assert ended.status == "ended"

    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            manager.end_session(tenant_id="tenant-1", session_id=session.session_id)
        )
    assert excinfo.value.code == "voice_session_ended"
    assert excinfo.value.status_code == 409


def test_manager_get_session_is_tenant_scoped() -> None:
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            manager.get_session(tenant_id="tenant-2", session_id=session.session_id)
        )
    assert excinfo.value.code == "voice_session_not_found"
    assert excinfo.value.status_code == 404


def test_manager_emits_lifecycle_events(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="voice_service.events")
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    events = [record.voice_event["event"] for record in caplog.records]
    assert events == [
        "session_created",
        "turn_started",
        "STT_START",
        "transcription_completed",
        "runtime_response_generated",
        "tts_started",
        "synthesis_completed",
        "turn_completed",
    ]
    for record in caplog.records:
        assert record.voice_event["tenant_id"] == "tenant-1"


def test_manager_emits_latency_stage_timings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="voice_service.events")
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    by_event = {
        record.voice_event["event"]: record.voice_event for record in caplog.records
    }
    assert by_event["transcription_completed"]["stt_elapsed_ms"] >= 0
    assert by_event["runtime_response_generated"]["runtime_elapsed_ms"] >= 0
    assert by_event["synthesis_completed"]["tts_elapsed_ms"] >= 0
    completed = by_event["turn_completed"]
    assert completed["turn_elapsed_ms"] >= 0
    assert (
        completed["turn_elapsed_ms"]
        >= completed["stt_elapsed_ms"]
        + completed["runtime_elapsed_ms"]
        + completed["tts_elapsed_ms"]
    )
    assert completed["response_chars"] > 0
    assert completed["audio_bytes"] > 0


def test_manager_emits_failed_event(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="voice_service.events")
    manager = build_manager(stt=FailingSTTProvider())
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )
    assert result.response_text

    events = [record.voice_event["event"] for record in caplog.records]
    assert "turn_failed" in events
    failed = next(
        record.voice_event for record in caplog.records if record.voice_event["event"] == "turn_failed"
    )
    assert failed["stage"] == "stt"
    assert failed["error_code"] == "voice_stt_error"


def test_manager_integrates_with_real_agent_runtime_and_mongo_store() -> None:
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.services import AgentService

    database = FakeCoreDatabase([agent_document()])
    conversation_store = InMemoryConversationStore()
    runtime = AgentRuntime(
        configuration_loader=AgentService(AgentRepository(database)),
        provider=MockLLMProvider(),
        conversation_store=conversation_store,
    )
    manager = build_manager(runtime=runtime, store=MongoVoiceSessionStore(FakeVoiceSessionDatabase()))

    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    assert result.response_text == "Mock response: Mock transcription of customer audio."
    assert session.voice_id == "neutral-voice"
    context = asyncio.run(
        conversation_store.get(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    assert context is not None
    assert [message.role for message in context.messages] == ["system", "user", "assistant"]


def test_agent_runtime_http_client_calls_agent_service_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/agents/agent-1":
            assert request.url.params["tenant_id"] == "tenant-1"
            return httpx.Response(
                200,
                json={
                    "id": "agent-1",
                    "tenant_id": "tenant-1",
                    "name": "Receptionist",
                    "role": "customer support assistant",
                    "language": "en",
                    "voice_id": "neutral-voice",
                    "goals": [],
                    "allowed_tools": [],
                    "knowledge_sources": [],
                    "created_at": "2026-08-03T12:00:00Z",
                    "updated_at": "2026-08-03T12:00:00Z",
                },
            )
        if request.method == "POST" and request.url.path.endswith("/runtime/test"):
            body = json.loads(request.content)
            assert body == {"conversation_id": "conversation-1", "message": "Hello"}
            return httpx.Response(
                200,
                json={
                    "conversation_id": "conversation-1",
                    "agent_id": "agent-1",
                    "response": "Mock response: Hello",
                    "provider": "mock",
                    "model": "mock-agent-runtime-v1",
                    "request_id": "abc",
                },
            )
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "nope"}})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://agent-service:8000")
    runtime = AgentRuntimeHttpClient(base_url="http://agent-service:8000", client=client)

    agent = asyncio.run(runtime.get_agent(tenant_id="tenant-1", agent_id="agent-1"))
    result = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Hello",
        )
    )

    assert agent.voice_id == "neutral-voice"
    assert agent.language == "en"
    assert result.text == "Mock response: Hello"
    assert result.provider_name == "mock"
    assert result.model_name == "mock-agent-runtime-v1"


# --- Streaming TTS turn pipeline ---


class ChunkyTTSProvider:
    """Fake streaming provider yielding PCM in uneven blobs."""

    provider_name = "chunky"

    def __init__(self, blobs: list[bytes], *, fail_after: int | None = None) -> None:
        self._blobs = blobs
        self._fail_after = fail_after
        self.yielded_bytes = 0
        self.yielded_at_first_sink = -1
        self.closed = False

    async def synthesize(self, **kwargs: object) -> TTSResult:
        return TTSResult(
            audio=AudioChunk(data=b"".join(self._blobs), format="pcm"),
            provider=self.provider_name,
            content_type="audio/pcm",
        )

    def synthesize_stream(self, **kwargs: object) -> AsyncIterator[AudioChunk]:
        return self._generate()

    def note_sink(self) -> None:
        if self.yielded_at_first_sink < 0:
            self.yielded_at_first_sink = self.yielded_bytes

    async def _generate(self) -> AsyncIterator[AudioChunk]:
        try:
            for index, blob in enumerate(self._blobs):
                if self._fail_after is not None and index >= self._fail_after:
                    raise RuntimeError("tts stream failed")
                self.yielded_bytes += len(blob)
                yield AudioChunk(data=blob, format="pcm")
        finally:
            self.closed = True


def run_stream_turn(
    tts: object,
) -> tuple[object, list[AudioChunk], ChunkyTTSProvider | None]:
    manager = build_manager(tts=tts)
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    frames: list[AudioChunk] = []
    provider = tts if isinstance(tts, ChunkyTTSProvider) else None

    async def main() -> object:
        async def _sink(frame: AudioChunk) -> None:
            if provider is not None:
                provider.note_sink()
            frames.append(frame)

        return await manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
            audio_sink=_sink,
        )

    return asyncio.run(main()), frames, provider


def test_streaming_turn_sends_first_frame_before_stream_end() -> None:
    provider = ChunkyTTSProvider(
        [b"\x01\x02" * 50, b"\x03\x04" * 250, b"\x05\x06" * 200]
    )

    result, frames, _ = run_stream_turn(provider)

    assert result.audio_packets_streamed == 4
    assert result.audio.data == b""
    assert len(frames) == 4
    assert all(len(frame.data) == 320 for frame in frames)
    assert provider.yielded_at_first_sink == 600
    assert provider.yielded_at_first_sink < 1000


def test_streaming_turn_retains_partial_bytes_and_pads_final_flush() -> None:
    provider = ChunkyTTSProvider([b"\x07" * 100, b"\x08" * 500, b"\x09" * 400])

    result, frames, _ = run_stream_turn(provider)

    assert result.audio_packets_streamed == 4
    assert [len(frame.data) for frame in frames] == [320, 320, 320, 320]
    assert frames[0].data == b"\x07" * 100 + b"\x08" * 220
    assert frames[1].data == b"\x08" * 280 + b"\x09" * 40
    assert frames[2].data == b"\x09" * 320
    assert frames[3].data == b"\x09" * 40 + b"\x00" * 280


def test_streaming_turn_emits_first_audio_instrumentation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="voice_service.events")
    provider = ChunkyTTSProvider([b"\x01" * 640])

    run_stream_turn(provider)

    by_event = {
        record.voice_event["event"]: record.voice_event for record in caplog.records
    }
    assert by_event["tts_stream_started"]["text_chars"] > 0
    assert by_event["tts_first_audio_chunk"]["first_chunk_elapsed_ms"] >= 0
    completed = by_event["tts_audio_stream_completed"]
    assert completed["tts_stream_chunks"] == 1
    assert completed["tts_audio_bytes"] == 640
    assert completed["frames_sent"] == 2
    assert completed["completed"] is True
    assert by_event["synthesis_completed"]["tts_elapsed_ms"] >= 0
    assert by_event["turn_completed"]["audio_packets_streamed"] == 2


def test_streaming_error_after_audio_keeps_partial_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="voice_service.events")
    provider = ChunkyTTSProvider(
        [b"\x01" * 320, b"\x02" * 320, b"\x03" * 320], fail_after=2
    )

    result, frames, _ = run_stream_turn(provider)

    assert result.audio_packets_streamed == 2
    assert result.audio.data == b""
    assert len(frames) == 2
    by_event = {
        record.voice_event["event"]: record.voice_event for record in caplog.records
    }
    assert by_event["tts_stream_interrupted"]["frames_sent"] == 2
    assert "turn_failed" not in by_event


def test_streaming_error_before_first_audio_falls_back_to_buffered() -> None:
    provider = ChunkyTTSProvider([b"\x01" * 320], fail_after=0)

    result, frames, _ = run_stream_turn(provider)

    assert result.audio.data == b"\x01" * 320
    assert result.audio_packets_streamed == 0
    assert frames == []


def test_streaming_empty_response_falls_back_to_buffered() -> None:
    provider = ChunkyTTSProvider([])

    result, frames, _ = run_stream_turn(provider)

    assert result.audio.data == b""
    assert result.audio_packets_streamed == 0


def test_streaming_cancellation_closes_provider_stream() -> None:
    provider = ChunkyTTSProvider([b"\x01" * 640])
    cleaned: list[bool] = []

    async def never_ends() -> AsyncIterator[AudioChunk]:
        try:
            yield AudioChunk(data=b"\x01" * 640, format="pcm")
            await asyncio.Future()
            yield AudioChunk(data=b"", format="pcm")
        finally:
            cleaned.append(True)

    provider.synthesize_stream = lambda **kwargs: never_ends()  # type: ignore[method-assign]
    manager = build_manager(tts=provider)
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    async def main() -> object:
        task = asyncio.create_task(
            manager.process_audio_input(
                tenant_id="tenant-1",
                session_id=session.session_id,
                audio=AudioChunk(data=b"audio", format="pcm"),
                audio_sink=lambda frame: asyncio.sleep(0),
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        return await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main())
    assert cleaned == [True]


def test_mock_provider_streams_through_sink_with_buffered_fallback() -> None:
    manager = build_manager()
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    frames: list[AudioChunk] = []

    async def main() -> object:
        async def _sink(frame: AudioChunk) -> None:
            frames.append(frame)

        return await manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
            audio_sink=_sink,
        )

    result = asyncio.run(main())

    # Mock audio is tiny text bytes: either it frames into ≥1 streamed
    # packet (empty buffered payload) or it falls back to buffered audio.
    # Both outcomes are valid; the invariant is they never mix.
    assert len(frames) == result.audio_packets_streamed
    assert (result.audio.data == b"") == (result.audio_packets_streamed > 0)


def test_pcm_frame_accumulator_splits_and_flushes() -> None:
    from voice_service.audio import PcmFrameAccumulator

    accumulator = PcmFrameAccumulator()
    assert accumulator.append(b"\x01" * 100) == []
    frames = accumulator.append(b"\x02" * 500)
    assert [len(frame.data) for frame in frames] == [320]
    assert accumulator.append(b"") == []
    final = accumulator.flush()
    assert final is not None
    assert len(final.data) == 320
    assert final.data == b"\x02" * 280 + b"\x00" * 40
    assert accumulator.flush() is None


# --- Turn deadlines, timeouts, greeting cache, barge-in ---


class HangingSTTProvider:
    async def transcribe(self, audio: AudioChunk) -> STTResult:
        await asyncio.sleep(30)
        return STTResult(text="too late", provider="hanging")


class HangingTTSProvider:
    provider_name = "hanging"

    async def synthesize(self, **kwargs: object) -> TTSResult:
        await asyncio.sleep(30)
        raise AssertionError("unreachable")

    def synthesize_stream(self, **kwargs: object) -> AsyncIterator[AudioChunk]:
        return self._generate()

    async def _generate(self) -> AsyncIterator[AudioChunk]:
        await asyncio.sleep(30)
        yield AudioChunk(data=b"", format="pcm")


class HangingAgentRuntime:
    async def get_agent(self, **kwargs: object) -> AgentConfiguration:
        return AgentConfiguration(id="agent-1", tenant_id="tenant-1")

    async def respond(self, **kwargs: object) -> RuntimeResult:
        await asyncio.sleep(30)
        raise AssertionError("unreachable")


class FlakySTTProvider:
    """Hangs once, then transcribes: proves the single STT retry."""

    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, audio: AudioChunk) -> STTResult:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(30)
        return STTResult(text="recovered speech", provider="flaky")


def test_stt_timeout_falls_back_without_hanging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import time

    from voice_service.config import TurnSettings

    caplog.set_level(logging.INFO, logger="voice_service.events")
    manager = build_manager(stt=HangingSTTProvider())
    manager._turn_settings = TurnSettings(  # type: ignore[attr-defined]
        turn_timeout=5.0, stt_timeout=0.05, runtime_timeout=5.0, tts_timeout=5.0
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    started = time.monotonic()
    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    assert time.monotonic() - started < 5.0
    assert "repeat your request" in result.response_text
    failed = next(
        record.voice_event
        for record in caplog.records
        if record.voice_event["event"] == "turn_failed"
    )
    assert failed["stage"] == "stt"
    assert failed["timeout"] is True


def test_runtime_timeout_falls_back_without_hanging() -> None:
    import time

    from voice_service.config import TurnSettings

    manager = build_manager(runtime=HangingAgentRuntime())
    manager._turn_settings = TurnSettings(  # type: ignore[attr-defined]
        turn_timeout=5.0, stt_timeout=5.0, runtime_timeout=0.05, tts_timeout=5.0
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    started = time.monotonic()
    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    assert time.monotonic() - started < 5.0
    assert "trouble reaching our systems" in result.response_text


def test_tts_timeout_returns_empty_audio_without_hanging() -> None:
    import time

    from voice_service.config import TurnSettings

    manager = build_manager(tts=HangingTTSProvider())
    manager._turn_settings = TurnSettings(  # type: ignore[attr-defined]
        turn_timeout=5.0, stt_timeout=5.0, runtime_timeout=5.0, tts_timeout=0.05
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    started = time.monotonic()
    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    assert time.monotonic() - started < 5.0
    assert result.audio.data == b""
    current = asyncio.run(
        manager.get_session(tenant_id="tenant-1", session_id=session.session_id)
    )
    assert current.status == "active"


def test_greeting_cache_serves_second_call_without_synthesize(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from voice_service.agent_runtime import AgentConfiguration

    caplog.set_level(logging.INFO, logger="voice_service.events")
    synthesizes = 0

    class CountingTTSProvider(MockTTSProvider):
        async def synthesize(self, **kwargs: object) -> TTSResult:
            nonlocal synthesizes
            synthesizes += 1
            return await super().synthesize(**kwargs)

    def agent_with_greeting(greeting: str) -> AgentConfiguration:
        return AgentConfiguration(
            id="agent-1",
            tenant_id="tenant-1",
            language="en",
            voice_id="neutral-voice",
            greeting=greeting,
        )

    manager = build_manager(
        tts=CountingTTSProvider(),
        runtime=FakeAgentRuntimeClient(agent=agent_with_greeting("Hello there")),
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    async def main() -> tuple[AudioChunk | None, AudioChunk | None]:
        first = await manager.synthesize_greeting(
            tenant_id="tenant-1", session_id=session.session_id
        )
        second = await manager.synthesize_greeting(
            tenant_id="tenant-1", session_id=session.session_id
        )
        return first, second

    first, second = asyncio.run(main())

    assert first is not None and second is not None
    assert first.data == second.data
    assert synthesizes == 1
    cached_flags = [
        record.voice_event.get("greeting_cached")
        for record in caplog.records
        if record.voice_event["event"] == "audio_synthesized"
    ]
    assert cached_flags == [False, True]


def test_greeting_cache_invalidates_on_text_change() -> None:
    from voice_service.agent_runtime import AgentConfiguration

    synthesizes = 0

    class CountingTTSProvider(MockTTSProvider):
        async def synthesize(self, **kwargs: object) -> TTSResult:
            nonlocal synthesizes
            synthesizes += 1
            return await super().synthesize(**kwargs)

    manager = build_manager(tts=CountingTTSProvider())

    async def greet_with(text: str) -> AudioChunk | None:
        runtime = FakeAgentRuntimeClient(
            agent=AgentConfiguration(
                id="agent-1",
                tenant_id="tenant-1",
                language="en",
                voice_id="neutral-voice",
                greeting=text,
            )
        )
        manager._agent_runtime = runtime  # type: ignore[attr-defined]
        session = await manager.create_session(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id=f"conversation-{text}",
        )
        return await manager.synthesize_greeting(
            tenant_id="tenant-1", session_id=session.session_id
        )

    async def main() -> None:
        await greet_with("Hello there")
        await greet_with("Hello there")
        await greet_with("Changed greeting")

    asyncio.run(main())

    assert synthesizes == 2


def test_greeting_cache_key_changes_with_configuration() -> None:
    from voice_service.greeting_cache import greeting_cache_key

    base = dict(
        tenant_id="tenant-1",
        agent_id="agent-1",
        text="Hello",
        voice_id="voice-1",
        model="model-1",
        output_format="pcm",
    )
    key = greeting_cache_key(**base)
    assert greeting_cache_key(**{**base, "text": "Hi"}) != key
    assert greeting_cache_key(**{**base, "voice_id": "voice-2"}) != key
    assert greeting_cache_key(**{**base, "model": "model-2"}) != key
    assert greeting_cache_key(**{**base, "agent_id": "agent-2"}) != key
    assert greeting_cache_key(**base) == key


class VoiceRecordingTTSProvider(MockTTSProvider):
    """Mock TTS recording the voice_id of every synthesis."""

    def __init__(self) -> None:
        super().__init__()
        self.voice_ids: list[str | None] = []

    async def synthesize(self, **kwargs: object) -> TTSResult:
        self.voice_ids.append(kwargs.get("voice_id"))  # type: ignore[arg-type]
        return await super().synthesize(**kwargs)


def _manager_with_agent_greeting(
    *, greeting: str | None, voice_id: str | None
) -> tuple[VoiceSessionManager, object]:
    from voice_service.agent_runtime import AgentConfiguration

    tts = VoiceRecordingTTSProvider()
    runtime = FakeAgentRuntimeClient(
        agent=AgentConfiguration(
            id="agent-1",
            tenant_id="tenant-1",
            language="en",
            voice_id=voice_id,
            greeting=greeting,
        )
    )
    return build_manager(tts=tts, runtime=runtime), tts


def test_greeting_uses_agent_voice_id() -> None:
    manager, tts = _manager_with_agent_greeting(
        greeting="Welcome in.", voice_id="agent-voice-1"
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    audio = asyncio.run(
        manager.synthesize_greeting(
            tenant_id="tenant-1", session_id=session.session_id
        )
    )

    assert audio is not None
    assert audio.data != b""
    assert tts.voice_ids == ["agent-voice-1"]


def test_no_greeting_configured_synthesizes_nothing() -> None:
    manager, tts = _manager_with_agent_greeting(greeting=None, voice_id="agent-voice-1")
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    audio = asyncio.run(
        manager.synthesize_greeting(
            tenant_id="tenant-1", session_id=session.session_id
        )
    )

    assert audio is None
    assert tts.voice_ids == []
    assert "Kaari" not in (session.metadata.get("greeting") or "")


def test_greeting_without_voice_id_uses_provider_default() -> None:
    manager, tts = _manager_with_agent_greeting(
        greeting="Welcome in.", voice_id=None
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    audio = asyncio.run(
        manager.synthesize_greeting(
            tenant_id="tenant-1", session_id=session.session_id
        )
    )

    assert audio is not None
    assert tts.voice_ids == [None]


def test_greeting_and_turn_share_resolved_voice_id() -> None:
    manager, tts = _manager_with_agent_greeting(
        greeting="Welcome in.", voice_id="agent-voice-1"
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    async def main() -> None:
        await manager.synthesize_greeting(
            tenant_id="tenant-1", session_id=session.session_id
        )
        await manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )

    asyncio.run(main())

    assert tts.voice_ids == ["agent-voice-1", "agent-voice-1"]


def test_stt_timeout_retries_once_then_recovers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from voice_service.config import TurnSettings

    caplog.set_level(logging.INFO, logger="voice_service.events")
    provider = FlakySTTProvider()
    manager = build_manager(stt=provider)
    manager._turn_settings = TurnSettings(  # type: ignore[attr-defined]
        turn_timeout=5.0, stt_timeout=0.05, runtime_timeout=5.0, tts_timeout=5.0
    )
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    result = asyncio.run(
        manager.process_audio_input(
            tenant_id="tenant-1",
            session_id=session.session_id,
            audio=AudioChunk(data=b"audio", format="pcm"),
        )
    )

    assert provider.calls == 2
    assert result.transcript == "recovered speech"
    assert any(
        record.voice_event["event"] == "stt_retry" for record in caplog.records
    )
