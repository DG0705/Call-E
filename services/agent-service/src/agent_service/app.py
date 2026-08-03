"""Agent service application assembly."""

from fastapi import FastAPI

from agent_service.database import CoreDatabase, create_core_database
from agent_service.routes.core import router as core_router
from agent_service.services import AgentService, TenantService
from call_e_shared import create_app


AGENT_SERVICE_NAME = "agent-service"


def create_agent_app(
    *,
    tenant_service: TenantService | None = None,
    agent_service: AgentService | None = None,
    core_database: CoreDatabase | None = None,
) -> FastAPI:
    """Create the service hosting the minimal tenant and agent core."""
    app = create_app(AGENT_SERVICE_NAME)
    database = core_database or (
        None if tenant_service is not None and agent_service is not None else create_core_database()
    )
    app.state.tenant_service = tenant_service or database.tenant_service
    app.state.agent_service = agent_service or database.agent_service
    app.include_router(core_router)

    if database is not None:

        @app.on_event("shutdown")
        async def close_core_database() -> None:
            await database.close()

    return app
