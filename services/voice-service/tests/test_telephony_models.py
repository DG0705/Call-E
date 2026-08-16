"""Tests for the telephony domain models."""

from datetime import UTC, datetime

from voice_service.telephony.models import TelephonyCall


def test_telephony_call_roundtrips_mongo_id() -> None:
    call = TelephonyCall.model_validate(
        {
            "_id": "call-1",
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
            "caller_number": "+15550001",
            "destination_number": "+15550002",
            "direction": "inbound",
            "status": "active",
            "provider": "mock",
            "created_at": "2026-08-10T12:00:00Z",
            "updated_at": "2026-08-10T12:00:00Z",
        }
    )

    assert call.call_id == "call-1"
    assert call.status == "active"
    assert call.direction == "inbound"
    assert call.model_dump()["call_id"] == "call-1"
    assert call.model_dump(by_alias=True)["_id"] == "call-1"


def test_telephony_call_defaults_to_ringing_with_empty_metadata() -> None:
    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conversation-1",
        destination_number="+15550002",
        direction="outbound",
        created_at=now,
        updated_at=now,
    )

    assert call.status == "ringing"
    assert call.provider == "mock"
    assert call.caller_number is None
    assert call.ended_at is None
    assert call.error_code is None
    assert call.metadata == {}
