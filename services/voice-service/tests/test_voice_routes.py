"""Tests for the voice session HTTP routes."""

import base64

from fastapi.testclient import TestClient

from voice_service.agent_runtime import AgentConfiguration, RuntimeResult
from voice_service.app import create_voice_app
from voice_service.session_store import InMemoryVoiceSessionStore
from voice_service.stt import MockSTTProvider
from voice_service.tts import MockTTSProvider


class FakeAgentRuntimeClient:
    """Deterministic runtime boundary used by the route tests."""

    def __init__(
        self,
        *,
        available: bool = True,
        respond_error: Exception | None = None,
    ) -> None:
        self.available = available
        self.respond_error = respond_error

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration:
        if not self.available:
            raise RuntimeError("agent unavailable")
        return AgentConfiguration(
            id=agent_id, tenant_id=tenant_id, language="en", voice_id="neutral-voice"
        )

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        if self.respond_error is not None:
            raise self.respond_error
        return RuntimeResult(
            text=f"Reply to: {message}",
            provider_name="mock",
            model_name="mock-agent-runtime-v1",
            conversation_id=conversation_id,
            agent_id=agent_id,
        )


def build_client(*, agent_runtime: object | None = None) -> TestClient:
    store = InMemoryVoiceSessionStore()
    return TestClient(
        create_voice_app(
            session_store=store,
            agent_runtime=agent_runtime or FakeAgentRuntimeClient(),  # type: ignore[arg-type]
            stt_provider=MockSTTProvider(),
            tts_provider=MockTTSProvider(),
        )
    )


def create_session(
    client: TestClient,
    *,
    tenant_id: str = "tenant-1",
    agent_id: str = "agent-1",
    conversation_id: str = "conversation-1",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/voice/sessions",
        json={
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "conversation_id": conversation_id,
            "output_audio_format": "pcm",
        },
    )
    assert response.status_code == 200
    return response.json()


def turn_payload(audio: bytes, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "tenant_id": "tenant-1",
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "audio_format": "pcm",
    }
    payload.update(overrides)
    return payload


def test_create_session_route_returns_tenant_scoped_session() -> None:
    client = build_client()

    session = client.post(
        "/api/v1/voice/sessions",
        headers={"X-Request-ID": "create-request"},
        json={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
            "voice_id": "custom-voice",
            "metadata": {"channel": "web-demo"},
        },
    )

    assert session.status_code == 200
    body = session.json()
    assert body["status"] == "created"
    assert body["tenant_id"] == "tenant-1"
    assert body["agent_id"] == "agent-1"
    assert body["voice_id"] == "custom-voice"
    assert body["metadata"] == {"channel": "web-demo"}
    assert "_id" not in body
    assert session.headers["X-Request-ID"] == "create-request"


def test_create_session_route_fails_when_agent_unavailable() -> None:
    client = build_client(agent_runtime=FakeAgentRuntimeClient(available=False))

    response = client.post(
        "/api/v1/voice/sessions",
        json={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "voice_agent_unavailable"


def test_turn_route_runs_full_audio_pipeline() -> None:
    client = build_client()
    session = create_session(client)

    response = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/turn",
        headers={"X-Request-ID": "turn-request"},
        json=turn_payload(b"customer-audio"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "Mock transcription of customer audio."
    assert body["response"] == "Reply to: Mock transcription of customer audio."
    assert body["audio_format"] == "pcm"
    assert body["content_type"] == "audio/pcm"
    assert body["stt_provider"] == "mock"
    assert body["tts_provider"] == "mock"
    assert body["request_id"] == "turn-request"
    assert base64.b64decode(body["audio_base64"]) == body["response"].encode()
    assert response.headers["X-Request-ID"] == "turn-request"


def test_turn_route_accepts_wav_input_and_returns_wav() -> None:
    client = build_client()
    session = create_session(client, agent_id="agent-1")
    wav_bytes = (
        b"RIFF"
        + (36 + 4).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (8000).to_bytes(4, "little")
        + (16000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (4).to_bytes(4, "little")
        + b"abcd"
    )

    response = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/turn",
        json=turn_payload(wav_bytes, audio_format="wav"),
    )

    assert response.status_code == 200
    assert response.json()["transcript"] == "Mock transcription of customer audio."


def test_turn_route_rejects_invalid_base64() -> None:
    client = build_client()
    session = create_session(client)

    response = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/turn",
        json={"tenant_id": "tenant-1", "audio_base64": "!!!not-base64!!!"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_audio_payload"


def test_turn_route_returns_404_for_unknown_session() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/voice/sessions/missing-session/turn",
        json=turn_payload(b"audio"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "voice_session_not_found"


def test_turn_route_returns_409_after_session_ended() -> None:
    client = build_client()
    session = create_session(client)
    client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/end",
        json={"tenant_id": "tenant-1"},
    )

    response = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/turn",
        json=turn_payload(b"audio"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "voice_session_ended"


def test_end_route_ends_session_and_prevents_repeat() -> None:
    client = build_client()
    session = create_session(client)

    ended = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/end",
        json={"tenant_id": "tenant-1"},
    )
    repeat = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/end",
        json={"tenant_id": "tenant-1"},
    )

    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "voice_session_ended"


def test_get_session_route_is_tenant_scoped() -> None:
    client = build_client()
    session = create_session(client)

    own = client.get(f"/api/v1/voice/sessions/{session['session_id']}?tenant_id=tenant-1")
    other = client.get(f"/api/v1/voice/sessions/{session['session_id']}?tenant_id=tenant-2")

    assert own.status_code == 200
    assert own.json()["status"] == "created"
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "voice_session_not_found"


def test_error_envelope_propagates_request_id() -> None:
    client = build_client()

    response = client.get(
        "/api/v1/voice/sessions/missing-session?tenant_id=tenant-1",
        headers={"X-Request-ID": "error-request"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "voice_session_not_found",
        "message": "Voice session was not found.",
        "request_id": "error-request",
    }
    assert response.headers["X-Request-ID"] == "error-request"


def test_stt_no_transcript_returns_422() -> None:
    from voice_service.audio import AudioChunk
    from voice_service.session_store import VoiceSessionStore
    from voice_service.stt import STTProvider, STTResult

    class EmptyTranscriptSTTProvider:
        async def transcribe(self, audio: AudioChunk) -> STTResult:
            return STTResult(text="", provider="mock-empty")

    store = InMemoryVoiceSessionStore()
    client = TestClient(
        create_voice_app(
            session_store=store,
            agent_runtime=FakeAgentRuntimeClient(),
            stt_provider=EmptyTranscriptSTTProvider(),  # type: ignore[arg-type]
            tts_provider=MockTTSProvider(),
        )
    )
    session = create_session(client)

    response = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/turn",
        json=turn_payload(b"audio"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "stt_no_transcript"


def test_voice_app_end_to_end_with_real_agent_runtime() -> None:
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
    client = build_client(agent_runtime=runtime)

    session = create_session(client)
    response = client.post(
        f"/api/v1/voice/sessions/{session['session_id']}/turn",
        json=turn_payload(b"customer-audio"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Mock response: Mock transcription of customer audio."
    assert body["audio_format"] == "pcm"
