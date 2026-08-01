"""Public gateway status route."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel


router = APIRouter(prefix="/api/v1", tags=["platform"])


class GatewayStatusResponse(BaseModel):
    """Stable public status payload for the API Gateway."""

    service_name: str
    status: str = "healthy"
    request_id: str | None = None
    version: Literal["v1"] = "v1"


@router.get("/status", response_model=GatewayStatusResponse)
async def platform_status(request: Request) -> GatewayStatusResponse:
    """Return the current gateway status for public platform checks."""
    return GatewayStatusResponse(
        service_name=request.app.title,
        request_id=getattr(request.state, "request_id", None),
    )
