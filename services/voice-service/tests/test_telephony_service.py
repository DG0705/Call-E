"""Tests for the telephony integration layer."""

import asyncio
import logging

import pytest

from call_e_shared.exceptions import PlatformError

from voice_service.agent_runtime import AgentConfiguration, RuntimeResult
from voice_service.audio import AudioChunk
from voice_service.session import VoiceSessionManager
from voice_service.session_store import InMemoryVoiceSessionStore
from voice_service.stt import MockSTTProvider
from voice_service.telephony import events
from voice_service.telephony.mock_provider import MockTelephonyProvider
from voice_service.telephony.provider import TelephonyProvider
from voice_service.telephony.service import TelephonyService
from voice_service.telephony.store import InMemoryCallStore
from voice_service.tts import MockTTSProvider


class FakeAgentRuntimeClient:
    """Deterministic agent boundary used by the integration tests."""

    def __init__(self) -> None:
        self.agent = AgentConfiguration(
            id="agent-1", tenant_id="tenant-1", language="en", voice_id="neutral-voice"
        )

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration:
        return self.agent

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        return RuntimeResult(
            text=f"Reply to: {message}",
            provider_name="mock",
            model_name="mock-agent-runtime-v1",
            conversation_id=conversation_id,
            agent_id=agent_id,
        )


class RecordingEventPublisher:
    """Capture every published lifecycle event."""

    def __init__(self) -> None:
        self.published: list[events.TelephonyEvent] = []

    async def publish(self, event: events.TelephonyEvent) -> None:
        self.published.append(event)


class FailingAnswerProvider(MockTelephonyProvider):
    """Provider that fails during answer to exercise failure handling."""

    async def answer_call(self, call: object, **kwargs: object) -> object:
        raise RuntimeError("pbx unreachable")


class FailingStartProvider(MockTelephonyProvider):
    """Provider that fails during outbound origination."""

    async def start_call(self, **kwargs: object) -> object:
        raise RuntimeError("pbx unreachable")


def build_service(
    *,
    provider: TelephonyProvider | None = None,
    runtime: object | None = None,
    publisher: RecordingEventPublisher | None = None,
    tts: object | None = None,
) -> tuple[TelephonyService, RecordingEventPublisher]:
    publisher = publisher or RecordingEventPublisher()
    manager = VoiceSessionManager(
        stt_provider=MockSTTProvider(),
        tts_provider=tts or MockTTSProvider(),  # type: ignore[arg-type]
        agent_runtime=runtime or FakeAgentRuntimeClient(),  # type: ignore[arg-type]
        session_store=InMemoryVoiceSessionStore(),
    )
    service = TelephonyService(
        provider=provider or MockTelephonyProvider(),  # type: ignore[arg-type]
        call_store=InMemoryCallStore(),
        voice_manager=manager,
        event_publisher=publisher,
    )
    return service, publisher


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def test_outbound_call_flow_persists_and_emits_events() -> None:
    service, publisher = build_service()

    call = run(
        service.create_outbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            destination_number="+15550002",
            caller_number="+15550001",
            request_id="req-1",
        )
    )

    assert call.direction == "outbound"
    assert call.status == "ringing"
    assert call.provider == "mock"
    assert call.conversation_id
    loaded = run(service.get_call(tenant_id="tenant-1", call_id=call.call_id))
    assert loaded.call_id == call.call_id
    assert [event.name for event in publisher.published] == [
        events.CALL_CREATED,
        events.CALL_RINGING,
    ]
    assert all(event.request_id == "req-1" for event in publisher.published)


def test_inbound_call_flow_carries_caller_number() -> None:
    service, _ = build_service()

    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
            request_id="req-1",
        )
    )

    assert call.direction == "inbound"
    assert call.status == "ringing"
    assert call.caller_number == "+15550001"
    assert call.conversation_id == "conversation-1"


def test_answer_call_opens_voice_session_and_starts() -> None:
    service, publisher = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
            request_id="req-1",
        )
    )

    call = run(
        service.answer_call(
            tenant_id="tenant-1", call_id=call.call_id, request_id="req-1"
        )
    )

    assert call.status == "active"
    assert call.metadata["session_id"]
    assert [event.name for event in publisher.published] == [
        events.CALL_CREATED,
        events.CALL_RINGING,
        events.CALL_ANSWERED,
        events.CALL_STARTED,
    ]
    started = next(
        event
        for event in publisher.published
        if event.name == events.CALL_STARTED
    )
    assert started.session_id == call.metadata["session_id"]
    assert started.conversation_id == "conversation-1"


def test_answer_channel_answers_without_opening_session() -> None:
    service, publisher = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
            request_id="req-1",
        )
    )

    call = run(
        service.answer_channel(
            tenant_id="tenant-1", call_id=call.call_id, request_id="req-1"
        )
    )

    assert call.status == "active"
    assert "session_id" not in call.metadata
    assert [event.name for event in publisher.published] == [
        events.CALL_CREATED,
        events.CALL_RINGING,
        events.CALL_ANSWERED,
    ]


def test_start_voice_session_requires_answered_call() -> None:
    service, _ = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )

    with pytest.raises(PlatformError) as excinfo:
        run(service.start_voice_session(tenant_id="tenant-1", call_id=call.call_id))

    assert excinfo.value.code == "call_not_answered"


def test_start_voice_session_after_answer_channel_starts_call() -> None:
    service, publisher = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
            request_id="req-1",
        )
    )
    call = run(
        service.answer_channel(
            tenant_id="tenant-1", call_id=call.call_id, request_id="req-1"
        )
    )

    call = run(
        service.start_voice_session(
            tenant_id="tenant-1", call_id=call.call_id, request_id="req-1"
        )
    )

    assert call.status == "active"
    assert call.metadata["session_id"]
    assert [event.name for event in publisher.published] == [
        events.CALL_CREATED,
        events.CALL_RINGING,
        events.CALL_ANSWERED,
        events.CALL_STARTED,
    ]


def test_answer_channel_failure_marks_call_failed() -> None:
    service, _ = build_service(provider=FailingAnswerProvider())
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )

    with pytest.raises(PlatformError):
        run(service.answer_channel(tenant_id="tenant-1", call_id=call.call_id))

    assert call.status == "failed"


def test_answer_call_plays_agent_greeting() -> None:
    runtime = FakeAgentRuntimeClient()
    runtime.agent = AgentConfiguration(
        id="agent-1",
        tenant_id="tenant-1",
        language="en",
        voice_id="neutral-voice",
        greeting="Welcome to Kaari Planters. How can I help you today?",
    )
    service, _ = build_service(runtime=runtime)
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))
    provider = service._provider  # type: ignore[attr-defined]

    assert call.status == "active"
    assert provider.sent_audio(call.call_id)  # type: ignore[attr-defined]


def test_answer_call_skips_greeting_when_agent_has_none() -> None:
    service, _ = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))
    provider = service._provider  # type: ignore[attr-defined]

    assert call.status == "active"
    assert not provider.sent_audio(call.call_id)  # type: ignore[attr-defined]


def test_answer_call_survives_greeting_tts_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from voice_service.stt import MockSTTProvider
    from voice_service.tts import TTSResult

    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")

    class FailingGreetingTTSProvider(MockTTSProvider):
        async def synthesize(self, **kwargs: object) -> TTSResult:
            raise RuntimeError("tts down")

    runtime = FakeAgentRuntimeClient()
    runtime.agent = AgentConfiguration(
        id="agent-1",
        tenant_id="tenant-1",
        language="en",
        voice_id="neutral-voice",
        greeting="Welcome to Kaari Planters. How can I help you today?",
    )
    manager = VoiceSessionManager(
        stt_provider=MockSTTProvider(),
        tts_provider=FailingGreetingTTSProvider(),
        agent_runtime=runtime,  # type: ignore[arg-type]
        session_store=InMemoryVoiceSessionStore(),
    )
    service = TelephonyService(
        provider=MockTelephonyProvider(),  # type: ignore[arg-type]
        call_store=InMemoryCallStore(),
        voice_manager=manager,
        event_publisher=RecordingEventPublisher(),
    )
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )

    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))

    # Greeting TTS failure must not fail the call: turns can still proceed.
    assert call.status == "active"
    failed = [
        record.telephony_event
        for record in caplog.records
        if getattr(record, "telephony_event", None) is not None
        and record.telephony_event["event"] == "greeting_failed"
    ]
    assert len(failed) == 1
    assert failed[0]["stage"] == "greeting_tts"


def test_answer_call_emits_greeting_stage_events(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")
    runtime = FakeAgentRuntimeClient()
    runtime.agent = AgentConfiguration(
        id="agent-1",
        tenant_id="tenant-1",
        language="en",
        voice_id="neutral-voice",
        greeting="Welcome to Kaari Planters. How can I help you today?",
    )
    service, _ = build_service(runtime=runtime)
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )

    run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))

    stages = [
        record.telephony_event["event"]
        for record in caplog.records
        if getattr(record, "telephony_event", None) is not None
        and record.telephony_event["event"].startswith("GREETING")
    ]
    assert stages == [
        "GREETING_START",
        "GREETING_TTS_COMPLETED",
        "GREETING_RTP_START",
        "GREETING_RTP_COMPLETED",
        "GREETING_COMPLETED",
    ]


def test_process_audio_runs_turn_and_sends_audio_back() -> None:
    service, _ = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))
    provider = service._provider  # type: ignore[attr-defined]

    provider.queue_audio(call.call_id, AudioChunk(data=b"customer-audio", format="pcm"))  # type: ignore[attr-defined]
    result = run(
        service.process_audio(
            tenant_id="tenant-1", call_id=call.call_id, audio=AudioChunk(data=b"customer-audio", format="pcm")
        )
    )

    assert result.transcript == "Mock transcription of customer audio."
    assert result.response_text == "Reply to: Mock transcription of customer audio."
    assert provider.sent_audio(call.call_id)  # type: ignore[attr-defined]


def test_process_audio_streams_chunky_tts_through_frame_sink(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from collections.abc import AsyncIterator

    from voice_service.tts import TTSResult

    class ChunkyServiceTTSProvider:
        provider_name = "chunky"

        async def synthesize(self, **kwargs: object) -> TTSResult:
            return TTSResult(
                audio=AudioChunk(data=b"\x01" * 640, format="pcm"),
                provider=self.provider_name,
                content_type="audio/pcm",
            )

        def synthesize_stream(self, **kwargs: object) -> AsyncIterator[AudioChunk]:
            return self._generate()

        async def _generate(self) -> AsyncIterator[AudioChunk]:
            yield AudioChunk(data=b"\x01" * 100, format="pcm")
            yield AudioChunk(data=b"\x02" * 540, format="pcm")

    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")
    service, _ = build_service(tts=ChunkyServiceTTSProvider())
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))
    provider = service._provider  # type: ignore[attr-defined]

    result = run(
        service.process_audio(
            tenant_id="tenant-1",
            call_id=call.call_id,
            audio=AudioChunk(data=b"customer-audio", format="pcm"),
        )
    )

    assert result.audio.data == b""
    assert result.audio_packets_streamed == 2
    sent = provider.sent_audio(call.call_id)  # type: ignore[attr-defined]
    assert [len(chunk.data) for chunk in sent] == [320, 320]
    returned = [
        record.telephony_event
        for record in caplog.records
        if getattr(record, "telephony_event", None) is not None
        and record.telephony_event["event"] == "audio_returned"
    ]
    assert len(returned) == 1
    assert returned[0]["rtp_packets"] == 2


def test_drain_audio_consumes_queued_chunks() -> None:
    service, _ = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))
    provider = service._provider  # type: ignore[attr-defined]
    provider.queue_audio(call.call_id, AudioChunk(data=b"one", format="pcm"))  # type: ignore[attr-defined]
    provider.queue_audio(call.call_id, AudioChunk(data=b"two", format="pcm"))  # type: ignore[attr-defined]

    results = run(
        service.drain_audio(tenant_id="tenant-1", call_id=call.call_id)
    )

    assert len(results) == 2


def test_hangup_ends_call_and_voice_session() -> None:
    service, publisher = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))
    session_id = call.metadata["session_id"]

    call = run(service.hangup(tenant_id="tenant-1", call_id=call.call_id))

    assert call.status == "ended"
    assert call.ended_at is not None
    assert publisher.published[-1].name == events.CALL_ENDED
    session = run(
        service._voice_manager.get_session(  # type: ignore[attr-defined]
            tenant_id="tenant-1", session_id=session_id
        )
    )
    assert session.status == "ended"


def test_get_call_is_tenant_scoped() -> None:
    service, _ = build_service()
    call = run(
        service.create_outbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            destination_number="+15550002",
        )
    )

    with pytest.raises(PlatformError) as excinfo:
        run(service.get_call(tenant_id="tenant-2", call_id=call.call_id))

    assert excinfo.value.code == "call_not_found"
    assert excinfo.value.status_code == 404


def test_unknown_call_returns_404() -> None:
    service, _ = build_service()

    with pytest.raises(PlatformError) as excinfo:
        run(service.get_call(tenant_id="tenant-1", call_id="missing"))

    assert excinfo.value.code == "call_not_found"


def test_process_audio_before_answer_returns_409() -> None:
    service, _ = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )

    with pytest.raises(PlatformError) as excinfo:
        run(
            service.process_audio(
                tenant_id="tenant-1",
                call_id=call.call_id,
                audio=AudioChunk(data=b"audio", format="pcm"),
            )
        )

    assert excinfo.value.code == "call_not_answered"
    assert excinfo.value.status_code == 409


def test_hangup_after_ended_returns_409() -> None:
    service, _ = build_service()
    call = run(
        service.create_outbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            destination_number="+15550002",
        )
    )
    run(service.hangup(tenant_id="tenant-1", call_id=call.call_id))

    with pytest.raises(PlatformError) as excinfo:
        run(service.hangup(tenant_id="tenant-1", call_id=call.call_id))

    assert excinfo.value.code == "call_ended"
    assert excinfo.value.status_code == 409


def test_provider_failure_maps_to_502() -> None:
    service, _ = build_service(provider=FailingStartProvider())

    with pytest.raises(PlatformError) as excinfo:
        run(
            service.create_outbound_call(
                tenant_id="tenant-1",
                agent_id="agent-1",
                destination_number="+15550002",
            )
        )

    assert excinfo.value.code == "telephony_provider_error"
    assert excinfo.value.status_code == 502


def test_answer_failure_marks_call_failed() -> None:
    service, publisher = build_service(provider=FailingAnswerProvider())
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )

    with pytest.raises(PlatformError) as excinfo:
        run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))

    assert excinfo.value.code == "telephony_provider_error"
    assert [event.name for event in publisher.published][-1] == events.CALL_FAILED
    loaded = run(service.get_call(tenant_id="tenant-1", call_id=call.call_id))
    assert loaded.status == "failed"
    assert loaded.error_code == "telephony_provider_error"


class FailingCreateCallStore(InMemoryCallStore):
    """Call store that fails persistence to exercise failure diagnostics."""

    async def create(self, call: object) -> None:
        raise RuntimeError("insert failed: password=hunter2 timeout after 1000ms")


def test_persist_failure_logs_safe_original_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = VoiceSessionManager(
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        agent_runtime=FakeAgentRuntimeClient(),  # type: ignore[arg-type]
        session_store=InMemoryVoiceSessionStore(),
    )
    service = TelephonyService(
        provider=MockTelephonyProvider(),  # type: ignore[arg-type]
        call_store=FailingCreateCallStore(),
        voice_manager=manager,
        event_publisher=RecordingEventPublisher(),
    )
    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")

    with pytest.raises(PlatformError) as excinfo:
        run(
            service.create_inbound_call(
                tenant_id="tenant-1",
                agent_id="agent-1",
                caller_number="+15550001",
                destination_number="+15550002",
                conversation_id="conversation-1",
            )
        )

    # PlatformError contract is unchanged.
    assert excinfo.value.code == "call_persistence_error"
    assert excinfo.value.status_code == 502
    failed = [
        record.telephony_event
        for record in caplog.records
        if record.telephony_event["event"] == "call_failed"
    ]
    assert len(failed) == 1
    assert failed[0]["error"] == "RuntimeError"
    assert failed[0]["error_code"] == "call_persistence_error"
    assert "timeout after 1000ms" in failed[0]["error_message"]
    assert "hunter2" not in failed[0]["error_message"]
    assert "password=***" in failed[0]["error_message"]
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.telephony_event["event"] == "call_failed"
    ]
    assert len(messages) == 1
    assert messages[0].startswith("call_failed ")
    assert "error=RuntimeError" in messages[0]
    assert "error_code=call_persistence_error" in messages[0]
    assert "timeout after 1000ms" in messages[0]
    assert "hunter2" not in messages[0]


def test_service_emits_structured_telephony_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")
    service, _ = build_service()

    call = run(
        service.create_outbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            destination_number="+15550002",
            request_id="req-1",
        )
    )

    events_logged = [
        record.telephony_event["event"] for record in caplog.records
    ]
    assert events_logged == ["call_created", "call_ringing"]
    assert all(
        record.telephony_event["tenant_id"] == "tenant-1" for record in caplog.records
    )
    assert all(
        record.telephony_event["request_id"] == "req-1" for record in caplog.records
    )


def test_mock_e2e_with_real_agent_runtime() -> None:
    from agent_service.repositories import AgentRepository
    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore
    from agent_service.services import AgentService

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
        def __init__(self) -> None:
            self.agents = FakeAgentCollection(
                [
                    {
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
                ]
            )

        async def list_collection_names(self, **kwargs: object) -> list[str]:
            return ["agents"]

        def __getitem__(self, name: str) -> FakeAgentCollection:
            assert name == "agents"
            return self.agents

    runtime = AgentRuntime(
        configuration_loader=AgentService(AgentRepository(FakeCoreDatabase())),
        provider=MockLLMProvider(),
        conversation_store=InMemoryConversationStore(),
    )
    provider = MockTelephonyProvider()
    service, publisher = build_service(provider=provider, runtime=runtime)

    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))
    provider.queue_audio(call.call_id, AudioChunk(data=b"customer-audio", format="pcm"))

    results = run(service.drain_audio(tenant_id="tenant-1", call_id=call.call_id))

    assert len(results) == 1
    assert results[0].response_text == "Mock response: Mock transcription of customer audio."
    assert len(provider.sent_audio(call.call_id)) == 1
    assert [event.name for event in publisher.published] == [
        events.CALL_CREATED,
        events.CALL_RINGING,
        events.CALL_ANSWERED,
        events.CALL_STARTED,
    ]


class CopyOnReadCallStore(InMemoryCallStore):
    """Call store with MongoDB copy semantics for reads and writes.

    In-memory stores hand out the identical object, so in-memory metadata
    mutations stay visible. MongoDB serializes on write and re-validates on
    every read, so only persisted fields survive. This fake snapshots on
    write and returns fresh validated copies on read, reproducing the
    production semantics that greeting delivery must survive.
    """

    async def create(self, call: object) -> None:
        import copy

        from voice_service.telephony.models import TelephonyCall

        assert isinstance(call, TelephonyCall)
        await super().create(
            TelephonyCall.model_validate(copy.deepcopy(call.model_dump(by_alias=True)))
        )

    async def get(self, *, tenant_id: str, call_id: str):  # type: ignore[no-untyped-def]
        import copy

        from voice_service.telephony.models import TelephonyCall

        stored = await super().get(tenant_id=tenant_id, call_id=call_id)
        if stored is None:
            return None
        return TelephonyCall.model_validate(
            copy.deepcopy(stored.model_dump(by_alias=True))
        )


class PlayMediaFailingTransport:
    """ARI transport whose play_media fails exactly like the real one."""

    def __init__(self) -> None:
        self.answered: list[str] = []
        self.hung_up: list[str] = []

    async def accept_inbound(
        self, *, caller_number: str, destination_number: str
    ) -> str:
        return "channel-1"

    async def answer(self, channel_id: str) -> None:
        self.answered.append(channel_id)

    async def hangup(self, channel_id: str) -> None:
        self.hung_up.append(channel_id)

    async def play_media(self, channel_id: str, media: bytes) -> None:
        from voice_service.telephony.asterisk.transport import (
            AsteriskTransportError,
        )

        raise AsteriskTransportError(
            "RTP media streaming is not implemented in this foundation."
        )


def test_greeting_delivery_survives_store_copy_semantics() -> None:
    import socket

    from voice_service.telephony.asterisk.adapter import AsteriskAdapter

    runtime = FakeAgentRuntimeClient()
    runtime.agent = AgentConfiguration(
        id="agent-1",
        tenant_id="tenant-1",
        language="en",
        voice_id="neutral-voice",
        greeting="Welcome to Kaari Planters. How can I help you today?",
    )
    manager = VoiceSessionManager(
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        agent_runtime=runtime,  # type: ignore[arg-type]
        session_store=InMemoryVoiceSessionStore(),
    )
    adapter = AsteriskAdapter(
        base_url="http://asterisk:8088",
        transport=PlayMediaFailingTransport(),  # type: ignore[arg-type]
    )
    service = TelephonyService(
        provider=adapter,  # type: ignore[arg-type]
        call_store=CopyOnReadCallStore(),
        voice_manager=manager,
        event_publisher=RecordingEventPublisher(),
    )
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(5)
    asterisk_port = receiver.getsockname()[1]

    async def main() -> None:
        try:
            call = await service.create_inbound_call(
                tenant_id="tenant-1",
                agent_id="agent-1",
                caller_number="+15550001",
                destination_number="+15550002",
                conversation_id="conversation-1",
            )
            adapter.bind_egress(
                call, remote_host="127.0.0.1", remote_port=asterisk_port
            )
            await service.answer_channel(
                tenant_id="tenant-1", call_id=call.call_id
            )
            await service.start_voice_session(
                tenant_id="tenant-1", call_id=call.call_id
            )
        finally:
            await adapter.close()

    try:
        run(main())
        packet, _ = receiver.recvfrom(4096)
    finally:
        receiver.close()

    # Greeting RTP reached the bound remote: version 2, PCMU payload type.
    assert len(packet) > 12
    assert packet[0] >> 6 == 2
    assert (packet[1] & 0x7F) == 0


def test_interrupt_audio_stops_active_playout_and_keeps_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from voice_service.telephony.mock_provider import MockTelephonyProvider
    from voice_service.tts import TTSResult

    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")
    caplog.set_level(logging.INFO, logger="voice_service.events")

    class ChunkySlowTTSProvider:
        provider_name = "chunky-slow"

        async def synthesize(self, **kwargs: object) -> TTSResult:
            return TTSResult(
                audio=AudioChunk(data=b"\x01" * 960, format="pcm"),
                provider=self.provider_name,
                content_type="audio/pcm",
            )

        def synthesize_stream(self, **kwargs: object) -> object:
            return self._generate()

        async def _generate(self) -> object:
            yield AudioChunk(data=b"\x01" * 480, format="pcm")
            yield AudioChunk(data=b"\x02" * 480, format="pcm")

    class GatedProvider(MockTelephonyProvider):
        """Holds the second frame open so barge-in lands mid-playout."""

        def __init__(self) -> None:
            super().__init__()
            self.gate: asyncio.Event = asyncio.Event()
            self.frames_seen = 0

        async def send_audio_frame(
            self, call: object, frame: AudioChunk, **kwargs: object
        ) -> int:
            from voice_service.telephony.models import TelephonyCall
            from voice_service.telephony.provider import AudioOutputInterrupted

            assert isinstance(call, TelephonyCall)
            abort = kwargs.get("abort")
            if abort is not None and abort.is_set():
                raise AudioOutputInterrupted("interrupted")
            self.frames_seen += 1
            if self.frames_seen >= 2:
                self.gate.set()
                await asyncio.sleep(5)
                if abort is not None and abort.is_set():
                    raise AudioOutputInterrupted("interrupted")
            assert isinstance(frame, AudioChunk)
            return await super().send_audio_frame(call, frame, **kwargs)

    provider = GatedProvider()
    service, _ = build_service(provider=provider, tts=ChunkySlowTTSProvider())
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))

    async def main() -> object:
        task = asyncio.create_task(
            service.process_audio(
                tenant_id="tenant-1",
                call_id=call.call_id,
                audio=AudioChunk(data=b"customer-audio", format="pcm"),
            )
        )
        while provider.frames_seen < 2:
            await asyncio.sleep(0.01)
        interrupted = await service.interrupt_audio(
            tenant_id="tenant-1", call_id=call.call_id
        )
        provider.gate.set()
        return await task, interrupted

    result, interrupted = run(main())

    assert interrupted is True
    # One frame played before the interrupt; the turn ends partial, not failed.
    assert result.audio_packets_streamed == 1
    assert result.audio.data == b""
    interrupted_events = [
        record.voice_event
        for record in caplog.records
        if getattr(record, "voice_event", None) is not None
        and record.voice_event["event"] == "tts_stream_interrupted"
    ]
    assert len(interrupted_events) == 1
    assert interrupted_events[0]["frames_sent"] == 1
    # Idle interrupt is a no-op.
    assert (
        run(
            service.interrupt_audio(tenant_id="tenant-1", call_id=call.call_id)
        )
        is False
    )
    # The call itself survives the interruption.
    assert (
        run(service.get_call(tenant_id="tenant-1", call_id=call.call_id))
    ).status == "active"


def test_interrupt_audio_ignores_stale_speech_outside_playout() -> None:
    service, _ = build_service()
    call = run(
        service.create_inbound_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            caller_number="+15550001",
            destination_number="+15550002",
            conversation_id="conversation-1",
        )
    )
    call = run(service.answer_call(tenant_id="tenant-1", call_id=call.call_id))

    # No playout window open: speech-like interrupt is a harmless no-op.
    assert (
        run(service.interrupt_audio(tenant_id="tenant-1", call_id=call.call_id))
        is False
    )
    assert (
        run(service.interrupt_audio(tenant_id="tenant-1", call_id="missing"))
        is False
    )
