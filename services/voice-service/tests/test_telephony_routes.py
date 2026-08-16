"""Tests for the telephony HTTP routes."""

from fastapi.testclient import TestClient

from voice_service.agent_runtime import AgentConfiguration, RuntimeResult
from voice_service.app import create_voice_app
from voice_service.session_store import InMemoryVoiceSessionStore
from voice_service.stt import MockSTTProvider
from voice_service.telephony.mock_provider import MockTelephonyProvider
from voice_service.telephony.store import InMemoryCallStore
from voice_service.tts import MockTTSProvider


class FakeAgentRuntimeClient:
    """Deterministic agent boundary used by the route tests."""

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration:
        return AgentConfiguration(
            id=agent_id, tenant_id=tenant_id, language="en", voice_id="neutral-voice"
        )

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


def build_client() -> TestClient:
    return TestClient(
        create_voice_app(
            session_store=InMemoryVoiceSessionStore(),
            call_store=InMemoryCallStore(),
            telephony_provider=MockTelephonyProvider(),
            agent_runtime=FakeAgentRuntimeClient(),
            stt_provider=MockSTTProvider(),
            tts_provider=MockTTSProvider(),
        )
    )


def create_call(
    client: TestClient,
    *,
    tenant_id: str = "tenant-1",
    agent_id: str = "agent-1",
    destination_number: str = "+15550002",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/telephony/calls",
        json={
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "destination_number": destination_number,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_call_route_originates_outbound_call() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/telephony/calls",
        headers={"X-Request-ID": "create-call"},
        json={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "destination_number": "+15550002",
            "caller_number": "+15550001",
            "conversation_id": "conversation-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ringing"
    assert body["direction"] == "outbound"
    assert body["provider"] == "mock"
    assert body["caller_number"] == "+15550001"
    assert body["conversation_id"] == "conversation-1"
    assert body["tenant_id"] == "tenant-1"
    assert "_id" not in body
    assert response.headers["X-Request-ID"] == "create-call"


def test_create_call_route_requires_destination_number() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/telephony/calls",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1"},
    )

    assert response.status_code == 422


def test_get_call_route_is_tenant_scoped() -> None:
    client = build_client()
    call = create_call(client)

    own = client.get(
        f"/api/v1/telephony/calls/{call['call_id']}?tenant_id=tenant-1"
    )
    other = client.get(
        f"/api/v1/telephony/calls/{call['call_id']}?tenant_id=tenant-2"
    )

    assert own.status_code == 200
    assert own.json()["status"] == "ringing"
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "call_not_found"


def test_hangup_route_ends_call_and_prevents_repeat() -> None:
    client = build_client()
    call = create_call(client)

    ended = client.post(
        f"/api/v1/telephony/calls/{call['call_id']}/hangup",
        json={"tenant_id": "tenant-1"},
    )
    repeat = client.post(
        f"/api/v1/telephony/calls/{call['call_id']}/hangup",
        json={"tenant_id": "tenant-1"},
    )

    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
    assert ended.json()["ended_at"] is not None
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "call_ended"


def test_error_envelope_propagates_request_id() -> None:
    client = build_client()

    response = client.get(
        "/api/v1/telephony/calls/missing-call?tenant_id=tenant-1",
        headers={"X-Request-ID": "error-request"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "call_not_found",
        "message": "Telephony call was not found.",
        "request_id": "error-request",
    }
    assert response.headers["X-Request-ID"] == "error-request"
