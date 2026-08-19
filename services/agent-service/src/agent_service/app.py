"""Agent service application assembly."""

from fastapi import FastAPI

from agent_service.database import CoreDatabase, create_core_database
from agent_service.kaari.service import KaariService
from agent_service.routes.core import router as core_router
from agent_service.routes.kaari import router as kaari_router
from agent_service.routes.runtime import router as runtime_router
from agent_service.runtime import (
    AgentRuntime,
    KnowledgeRetriever,
    LLMProvider,
    LLMProviderFactory,
)
from agent_service.runtime.config import LLMSettings, load_llm_settings
from agent_service.runtime.context import ConversationStore, InMemoryConversationStore
from agent_service.runtime.tools import ToolRegistry, create_development_tool_registry
from agent_service.services import AgentService, TenantService
from call_e_shared import create_app


AGENT_SERVICE_NAME = "agent-service"


def create_combined_tool_registry() -> ToolRegistry:
    """Create a tool registry containing both dev and Kaari sales tools."""
    kaari = KaariService()
    registry = kaari.create_tool_registry()
    dev_registry = create_development_tool_registry()
    for tool in dev_registry.list():
        if registry.get(tool.tool_name) is None:
            existing = dev_registry.get(tool.tool_name)
            if existing is not None:
                registry.register(existing)
    return registry


def create_agent_app(
    *,
    tenant_service: TenantService | None = None,
    agent_service: AgentService | None = None,
    core_database: CoreDatabase | None = None,
    agent_runtime: AgentRuntime | None = None,
    llm_provider: LLMProvider | None = None,
    llm_settings: LLMSettings | None = None,
    conversation_store: ConversationStore | None = None,
    tool_registry: ToolRegistry | None = None,
    knowledge_retriever: KnowledgeRetriever | None = None,
    knowledge_top_k: int = 3,
    kaari_service: KaariService | None = None,
) -> FastAPI:
    """Create the service hosting the minimal tenant and agent core."""
    app = create_app(AGENT_SERVICE_NAME)
    database = core_database or (
        None if tenant_service is not None and agent_service is not None else create_core_database()
    )
    app.state.tenant_service = tenant_service or database.tenant_service
    app.state.agent_service = agent_service or database.agent_service
    settings = llm_settings or load_llm_settings()

    kaari = kaari_service or KaariService()
    app.state.kaari_service = kaari

    combined_registry = tool_registry or create_combined_tool_registry()

    effective_knowledge = knowledge_retriever
    effective_top_k = knowledge_top_k

    app.state.agent_runtime = agent_runtime or AgentRuntime(
        configuration_loader=app.state.agent_service,
        provider=llm_provider or LLMProviderFactory.create(settings),
        conversation_store=conversation_store
        or (database.conversation_store if database is not None else InMemoryConversationStore()),
        tool_registry=combined_registry,
        max_tool_iterations=settings.max_tool_iterations,
        knowledge_retriever=effective_knowledge,
        knowledge_top_k=effective_top_k,
    )
    app.include_router(core_router)
    app.include_router(runtime_router)
    app.include_router(kaari_router)

    if database is not None:

        @app.on_event("startup")
        async def initialize_core_database() -> None:
            await database.initialize()

        @app.on_event("shutdown")
        async def close_core_database() -> None:
            await database.close()

    return app
