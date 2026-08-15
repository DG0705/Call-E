"""Agent service application assembly."""

from fastapi import FastAPI

from agent_service.database import CoreDatabase, create_core_database
from agent_service.routes.core import router as core_router
from agent_service.routes.runtime import router as runtime_router
from agent_service.runtime import AgentRuntime, LLMProvider, LLMProviderFactory
from agent_service.runtime.config import LLMSettings, load_llm_settings
from agent_service.runtime.context import ConversationStore, InMemoryConversationStore
from agent_service.services import AgentService, TenantService
from call_e_shared import create_app


AGENT_SERVICE_NAME = "agent-service"


def create_agent_app(
    *,
    tenant_service: TenantService | None = None,
    agent_service: AgentService | None = None,
    core_database: CoreDatabase | None = None,
    agent_runtime: AgentRuntime | None = None,
    llm_provider: LLMProvider | None = None,
    llm_settings: LLMSettings | None = None,
    conversation_store: ConversationStore | None = None,
) -> FastAPI:
    """Create the service hosting the minimal tenant and agent core."""
    app = create_app(AGENT_SERVICE_NAME)
    database = core_database or (
        None if tenant_service is not None and agent_service is not None else create_core_database()
    )
    app.state.tenant_service = tenant_service or database.tenant_service
    app.state.agent_service = agent_service or database.agent_service
    app.state.agent_runtime = agent_runtime or AgentRuntime(
        configuration_loader=app.state.agent_service,
        provider=llm_provider
        or LLMProviderFactory.create(llm_settings or load_llm_settings()),
        conversation_store=conversation_store
        or (database.conversation_store if database is not None else InMemoryConversationStore()),
    )
    app.include_router(core_router)
    app.include_router(runtime_router)

    if database is not None:

        @app.on_event("startup")
        async def initialize_core_database() -> None:
            await database.initialize()

        @app.on_event("shutdown")
        async def close_core_database() -> None:
            await database.close()

    return app
