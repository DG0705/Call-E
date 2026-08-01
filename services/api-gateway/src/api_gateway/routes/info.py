"""Public gateway information route."""

from fastapi import APIRouter, Request

from api_gateway.routes.status import GatewayStatusResponse


GATEWAY_DESCRIPTION = "Call-E public API Gateway"

router = APIRouter(prefix="/api/v1", tags=["platform"])


class GatewayInfoResponse(GatewayStatusResponse):
    """Stable public information payload for the API Gateway."""

    description: str = GATEWAY_DESCRIPTION


@router.get("/info", response_model=GatewayInfoResponse)
async def platform_info(request: Request) -> GatewayInfoResponse:
    """Return static public information about the API Gateway."""
    return GatewayInfoResponse(
        service_name=request.app.title,
        request_id=getattr(request.state, "request_id", None),
    )
