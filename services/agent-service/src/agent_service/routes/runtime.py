"""Development-only API for inspecting and exercising the agent runtime."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from agent_service.models import Agent
from agent_service.runtime.runtime import AgentNotFoundError, RuntimeResult
from call_e_shared.exceptions import PlatformError


router = APIRouter(tags=["agent-runtime"])


class RuntimeTestRequest(BaseModel):
    """Input accepted by the local runtime test endpoint."""

    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class RuntimeTestResponse(BaseModel):
    """Stable API response for a development runtime invocation."""

    conversation_id: str
    agent_id: str
    response: str
    provider: str
    model: str
    request_id: str | None = None


def _not_found() -> PlatformError:
    return PlatformError(code="agent_not_found", message="Agent was not found.", status_code=404)


@router.get("/api/v1/agents/{agent_id}", response_model=Agent)
async def get_agent(
    request: Request, agent_id: str, tenant_id: str = Query(min_length=1)
) -> Agent:
    """Return one tenant-scoped agent configuration."""
    try:
        return await request.app.state.agent_runtime.get_agent(
            tenant_id=tenant_id, agent_id=agent_id
        )
    except AgentNotFoundError as exc:
        raise _not_found() from exc


@router.post(
    "/api/v1/agents/{agent_id}/runtime/test", response_model=RuntimeTestResponse
)
async def test_runtime(
    request: Request,
    agent_id: str,
    payload: RuntimeTestRequest,
    tenant_id: str = Query(min_length=1),
) -> RuntimeTestResponse:
    """Run the local development provider without a voice or tool integration."""
    try:
        result: RuntimeResult = await request.app.state.agent_runtime.respond(
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=payload.conversation_id,
            message=payload.message,
        )
    except AgentNotFoundError as exc:
        raise _not_found() from exc
    return RuntimeTestResponse(
        conversation_id=result.conversation_id,
        agent_id=result.agent_id,
        response=result.text,
        provider=result.provider_name,
        model=result.model_name,
        request_id=getattr(request.state, "request_id", None),
    )
