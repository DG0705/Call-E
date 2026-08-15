"""Knowledge service application assembly."""

from fastapi import FastAPI

from call_e_shared import create_app
from knowledge_service.database import KnowledgeDatabase, create_in_memory_database
from knowledge_service.routes.knowledge import router as knowledge_router


KNOWLEDGE_SERVICE_NAME = "knowledge-service"


def create_knowledge_app(*, database: KnowledgeDatabase | None = None) -> FastAPI:
    """Create the service hosting knowledge ingestion and retrieval."""
    app = create_app(KNOWLEDGE_SERVICE_NAME)
    app.state.database = database or create_in_memory_database()
    app.state.source_service = app.state.database.source_service
    app.state.document_service = app.state.database.document_service
    app.state.ingestion_service = app.state.database.ingestion_service
    app.state.search_service = app.state.database.search_service
    app.include_router(knowledge_router)

    @app.on_event("startup")
    async def initialize_knowledge_database() -> None:
        await app.state.database.initialize()

    @app.on_event("shutdown")
    async def close_knowledge_database() -> None:
        await app.state.database.close()

    return app
