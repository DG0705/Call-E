"""Authentication foundation status route."""

from fastapi import APIRouter, Request

from call_e_shared import PlatformResponse, build_platform_response


AUTH_FOUNDATION_DESCRIPTION = "Call-E authentication foundation"

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/status", response_model=PlatformResponse, response_model_exclude_none=True)
async def auth_status(request: Request) -> PlatformResponse:
    """Return the status of the authentication foundation."""
    return build_platform_response(
        service_name=request.app.title,
        request_id=getattr(request.state, "request_id", None),
        description=AUTH_FOUNDATION_DESCRIPTION,
    )
