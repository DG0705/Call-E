"""FastAPI application for the knowledge-service service."""

from knowledge_service.app import create_knowledge_app
from knowledge_service.database import create_knowledge_database


app = create_knowledge_app(database=create_knowledge_database())
