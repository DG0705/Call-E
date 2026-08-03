"""Agent service application assembly."""

from fastapi import FastAPI

from agent_service.database import CoreDatabase, create_core_database
from agent_service.repositories import AgentRepository, TenantRepository
from agent_service.routes.core import router as core_router
from call_e_shared import create_app


AGENT_SERVICE_NAME = "agent-service"


def create_agent_app(
    *,
    tenant_repository: TenantRepository | None = None,
    agent_repository: AgentRepository | None = None,
    core_database: CoreDatabase | None = None,
) -> FastAPI:
    """Create the service hosting the minimal tenant and agent core."""
    app = create_app(AGENT_SERVICE_NAME)
    database = core_database or (
        None if tenant_repository is not None and agent_repository is not None else create_core_database()
    )
    app.state.tenant_repository = tenant_repository or database.tenants
    app.state.agent_repository = agent_repository or database.agents
    app.include_router(core_router)

    if database is not None:

        @app.on_event("shutdown")
        async def close_core_database() -> None:
            await database.close()

    return app
