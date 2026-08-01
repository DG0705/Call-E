"""Public gateway status route."""

from fastapi import APIRouter, Request

from call_e_shared.responses import HealthResponse


router = APIRouter(prefix="/api/v1", tags=["platform"])


@router.get("/status", response_model=HealthResponse)
async def platform_status(request: Request) -> HealthResponse:
    """Return the current gateway status for public platform checks."""
    return HealthResponse(
        service=request.app.title,
        request_id=getattr(request.state, "request_id", None),
    )
