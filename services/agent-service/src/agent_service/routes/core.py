"""Read-only platform core routes."""

from fastapi import APIRouter, Request

from agent_service.services import AgentService, TenantService
from call_e_shared import PlatformResponse, build_platform_response
from call_e_shared.exceptions import PlatformError


TENANT_DESCRIPTION = "Call-E tenant core"
AGENT_DESCRIPTION = "Call-E agent core"
TENANT_DATABASE_DESCRIPTION = "Tenant database connection verified"
AGENT_DATABASE_DESCRIPTION = "Agent database connection verified"

router = APIRouter(tags=["core"])


def _response(request: Request, description: str) -> PlatformResponse:
    return build_platform_response(
        service_name=request.app.title,
        request_id=getattr(request.state, "request_id", None),
        description=description,
    )


async def _ping_collection(service: TenantService | AgentService) -> None:
    try:
        await service.collection_exists()
    except Exception as exc:
        raise PlatformError(
            code="core_database_unavailable",
            message="Core database is unavailable.",
            status_code=503,
        ) from exc


@router.get("/api/v1/tenants/status", response_model=PlatformResponse, response_model_exclude_none=True)
async def tenant_status(request: Request) -> PlatformResponse:
    """Return the stable tenant core status."""
    return _response(request, TENANT_DESCRIPTION)


@router.get("/api/v1/tenants/ping-db", response_model=PlatformResponse, response_model_exclude_none=True)
async def ping_tenant_database(request: Request) -> PlatformResponse:
    """Verify tenant collection access without mutating data."""
    await _ping_collection(request.app.state.tenant_service)
    return _response(request, TENANT_DATABASE_DESCRIPTION)


@router.get("/api/v1/agents/status", response_model=PlatformResponse, response_model_exclude_none=True)
async def agent_status(request: Request) -> PlatformResponse:
    """Return the stable agent core status."""
    return _response(request, AGENT_DESCRIPTION)


@router.get("/api/v1/agents/ping-db", response_model=PlatformResponse, response_model_exclude_none=True)
async def ping_agent_database(request: Request) -> PlatformResponse:
    """Verify agent collection access without mutating data."""
    await _ping_collection(request.app.state.agent_service)
    return _response(request, AGENT_DATABASE_DESCRIPTION)
