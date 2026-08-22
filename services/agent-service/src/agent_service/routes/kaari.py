"""Development API for exercising the Kaari AI Sales Agent end-to-end."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from agent_service.runtime.runtime import AgentNotFoundError, RuntimeResult
from call_e_shared.exceptions import PlatformError


router = APIRouter(tags=["kaari-sales"])


class KaariTestRequest(BaseModel):
    """Input for the Kaari sales agent development test endpoint."""

    tenant_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class KaariTestResponse(BaseModel):
    """Stable API response for a Kaari sales agent test invocation."""

    conversation_id: str
    response: str
    tool_calls: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, object]] = Field(default_factory=list)
    lead_id: str | None = None
    pricing: dict[str, object] | None = None
    request_id: str | None = None


def _not_found() -> PlatformError:
    return PlatformError(
        code="kaari_agent_not_found",
        message="Kaari agent was not found.",
        status_code=404,
    )


@router.post(
    "/api/v1/kaari/sales/test",
    response_model=KaariTestResponse,
)
async def kaari_sales_test(
    request: Request,
    payload: KaariTestRequest,
) -> KaariTestResponse:
    """Run the Kaari AI Sales Agent through the complete workflow."""
    try:
        result: RuntimeResult = await request.app.state.agent_runtime.respond(
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            conversation_id=payload.conversation_id,
            message=payload.message,
        )
    except AgentNotFoundError as exc:
        raise _not_found() from exc

    return KaariTestResponse(
        conversation_id=result.conversation_id,
        response=result.text,
        tool_calls=[],
        tool_results=[],
        lead_id=None,
        pricing=None,
        request_id=getattr(request.state, "request_id", None),
    )
