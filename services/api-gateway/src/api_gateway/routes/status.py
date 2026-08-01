"""Public gateway status route."""

from fastapi import APIRouter, Request

from call_e_shared import PlatformResponse, build_platform_response


router = APIRouter(prefix="/api/v1", tags=["platform"])


@router.get("/status", response_model=PlatformResponse, response_model_exclude_none=True)
async def platform_status(request: Request) -> PlatformResponse:
    """Return the current gateway status for public platform checks."""
    return build_platform_response(
        service_name=request.app.title,
        request_id=getattr(request.state, "request_id", None),
    )
