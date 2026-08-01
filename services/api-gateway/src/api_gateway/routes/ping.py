"""Public gateway uptime route."""

from fastapi import APIRouter, Request

from call_e_shared import PlatformResponse, build_platform_response


router = APIRouter(prefix="/api/v1", tags=["platform"])


@router.get("/ping", response_model=PlatformResponse, response_model_exclude_none=True)
async def ping(request: Request) -> PlatformResponse:
    """Return a compact response for uptime checks."""
    return build_platform_response(
        service_name=request.app.title,
        status="ok",
        request_id=getattr(request.state, "request_id", None),
    )
