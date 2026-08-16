"""Provider-neutral telephony domain models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CALLS_COLLECTION = "calls"

CallDirection = Literal["inbound", "outbound"]
CallStatus = Literal["ringing", "answered", "active", "ended", "failed"]


class TelephonyCall(BaseModel):
    """Normalized lifecycle state for one telephony call."""

    model_config = ConfigDict(populate_by_name=True)

    call_id: str = Field(alias="_id")
    tenant_id: str
    agent_id: str
    conversation_id: str
    caller_number: str | None = None
    destination_number: str
    direction: CallDirection
    status: CallStatus = "ringing"
    provider: str = "mock"
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
