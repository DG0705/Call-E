"""Development API for the telephony call lifecycle."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from voice_service.telephony.models import TelephonyCall


router = APIRouter(tags=["telephony"])


class CreateCallRequest(BaseModel):
    """Input for originating an outbound call."""

    tenant_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    destination_number: str = Field(min_length=1)
    caller_number: str | None = None
    conversation_id: str | None = None


class HangupCallRequest(BaseModel):
    """Input for hanging up an existing call."""

    tenant_id: str = Field(min_length=1)


@router.post(
    "/api/v1/telephony/calls",
    response_model=TelephonyCall,
    response_model_by_alias=False,
)
async def create_call(request: Request, payload: CreateCallRequest) -> TelephonyCall:
    """Originate one outbound call through the configured provider."""
    return await request.app.state.telephony_service.create_outbound_call(
        tenant_id=payload.tenant_id,
        agent_id=payload.agent_id,
        destination_number=payload.destination_number,
        caller_number=payload.caller_number,
        conversation_id=payload.conversation_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/api/v1/telephony/calls/{call_id}",
    response_model=TelephonyCall,
    response_model_by_alias=False,
)
async def get_call(
    request: Request, call_id: str, tenant_id: str = Query(min_length=1)
) -> TelephonyCall:
    """Return the current lifecycle state of one telephony call."""
    return await request.app.state.telephony_service.get_call(
        tenant_id=tenant_id, call_id=call_id
    )


@router.post(
    "/api/v1/telephony/calls/{call_id}/hangup",
    response_model=TelephonyCall,
    response_model_by_alias=False,
)
async def hangup_call(
    request: Request, call_id: str, payload: HangupCallRequest
) -> TelephonyCall:
    """Hang up an active call and persist its ended state."""
    return await request.app.state.telephony_service.hangup(
        tenant_id=payload.tenant_id,
        call_id=call_id,
        request_id=getattr(request.state, "request_id", None),
    )
