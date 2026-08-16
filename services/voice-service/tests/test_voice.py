"""Tests for the voice service application logic."""

import asyncio
import json
import logging

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
        STTProviderFactory.create(STTSettings(provider="deepgram"))
    with pytest.raises(VoiceProviderConfigurationError):
        TTSProviderFactory.create(TTSSettings(provider="elevenlabs"))


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
        ([("tenant_id", 1), ("session_id", 1)], {"name": VOICE_SESSION_LOOKUP_INDEX, "unique": True})
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
    ("stage", "manager", "code"),
    [
        ("stt", build_manager(stt=FailingSTTProvider()), "voice_stt_error"),
        (
            "runtime",
            build_manager(runtime=FakeAgentRuntimeClient(respond_error=RuntimeError("boom"))),
            "voice_runtime_error",
        ),
        ("tts", build_manager(tts=FailingTTSProvider()), "voice_tts_error"),
    ],
)
def test_manager_marks_session_failed_when_pipeline_stage_fails(
    stage: str, manager: VoiceSessionManager, code: str
) -> None:
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

    assert excinfo.value.code == code
    assert excinfo.value.status_code == 502
    failed = asyncio.run(
        manager.get_session(tenant_id="tenant-1", session_id=session.session_id)
    )
    assert failed.status == "failed"
    assert failed.error_code == code


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
        "transcription_completed",
        "runtime_response_generated",
        "synthesis_completed",
    ]
    for record in caplog.records:
        assert record.voice_event["tenant_id"] == "tenant-1"


def test_manager_emits_failed_event(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="voice_service.events")
    manager = build_manager(stt=FailingSTTProvider())
    session = asyncio.run(
        manager.create_session(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    with pytest.raises(PlatformError):
        asyncio.run(
            manager.process_audio_input(
                tenant_id="tenant-1",
                session_id=session.session_id,
                audio=AudioChunk(data=b"audio", format="pcm"),
            )
        )

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
