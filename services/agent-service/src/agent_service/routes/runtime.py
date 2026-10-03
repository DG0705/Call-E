"""Development-only API for inspecting and exercising the agent runtime."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_service.models import Agent
from agent_service.runtime.runtime import (
    AgentNotFoundError,
    RuntimeResult,
    RuntimeStreamEvent,
)
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
    tool_iterations: int = 0
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
        tool_iterations=len(result.tool_execution_history),
        request_id=getattr(request.state, "request_id", None),
    )


def _format_sse(event: RuntimeStreamEvent) -> str:
    """Render one runtime event in SSE wire format (no content logged)."""
    return f"event: {event.type}\ndata: {event.model_dump_json(exclude={'result'})}\n\n"


def _format_sse_done(event: RuntimeStreamEvent) -> str:
    return f"event: done\ndata: {event.model_dump_json()}\n\n"


@router.post("/api/v1/agents/{agent_id}/runtime/stream")
async def stream_runtime(
    request: Request,
    agent_id: str,
    payload: RuntimeTestRequest,
    tenant_id: str = Query(min_length=1),
) -> StreamingResponse:
    """Stream one runtime turn as text/tool/done events (SSE).

    The synchronous ``runtime/test`` endpoint is unchanged. Unknown agents
    fail before streaming starts; mid-stream errors end the stream with an
    ``error`` event so callers can fall back to the buffered call.
    """

    async def event_source() -> AsyncIterator[str]:
        try:
            async for event in request.app.state.agent_runtime.respond_stream(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=payload.conversation_id,
                message=payload.message,
            ):
                if event.type == "done":
                    yield _format_sse_done(event)
                else:
                    yield _format_sse(event)
        except Exception as exc:
            yield f"event: error\ndata: {type(exc).__name__}\n\n"

    try:
        # Resolve the agent first so unknown agents 404 instead of streaming.
        await request.app.state.agent_runtime.get_agent(
            tenant_id=tenant_id, agent_id=agent_id
        )
    except AgentNotFoundError as exc:
        raise _not_found() from exc
    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post(
    "/api/v1/agents/{agent_id}/runtime/tool-test", response_model=RuntimeTestResponse
)
async def test_runtime_tools(
    request: Request,
    agent_id: str,
    payload: RuntimeTestRequest,
    tenant_id: str = Query(min_length=1),
) -> RuntimeTestResponse:
    """Exercise the development runtime path with registered safe tools."""
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
        tool_iterations=len(result.tool_execution_history),
        request_id=getattr(request.state, "request_id", None),
    )
