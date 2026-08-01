"""Public gateway information route."""

from fastapi import APIRouter, Request

from call_e_shared import PlatformResponse, build_platform_response


GATEWAY_DESCRIPTION = "Call-E public API Gateway"

router = APIRouter(prefix="/api/v1", tags=["platform"])


@router.get("/info", response_model=PlatformResponse, response_model_exclude_none=True)
async def platform_info(request: Request) -> PlatformResponse:
    """Return static public information about the API Gateway."""
    return build_platform_response(
        service_name=request.app.title,
        request_id=getattr(request.state, "request_id", None),
        description=GATEWAY_DESCRIPTION,
    )
