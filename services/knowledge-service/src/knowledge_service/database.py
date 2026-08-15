"""Knowledge database wiring for Mongo and in-memory persistence."""

import os
from typing import Any

from pymongo import AsyncMongoClient

from knowledge_service.embeddings import EmbeddingProvider, MockEmbeddingProvider
from knowledge_service.models import (
    KNOWLEDGE_CHUNKS_COLLECTION,
    KNOWLEDGE_DOCUMENTS_COLLECTION,
    KNOWLEDGE_SOURCES_COLLECTION,
)
from knowledge_service.repositories import (
    KnowledgeCollectionDatabase,
    KnowledgeCollectionSurface,
    KnowledgeDocumentRepository,
    KnowledgeSourceRepository,
)
from knowledge_service.retrieval import (
    AgentKnowledgeResolver,
    KnowledgeRetrieverService,
    MappingAgentKnowledgeResolver,
)
from knowledge_service.services import (
    KnowledgeDocumentService,
    KnowledgeIngestionService,
    KnowledgeSearchService,
    KnowledgeSourceService,
)
from knowledge_service.storage import CollectionVectorRepository


DEFAULT_KNOWLEDGE_DATABASE = "call_e_knowledge"
MONGODB_URL_ENV_VAR = "MONGODB_URL"
KNOWLEDGE_DATABASE_ENV_VAR = "KNOWLEDGE_DATABASE_NAME"

SOURCE_TENANT_INDEX = "source_tenant"
DOCUMENT_TENANT_SOURCE_INDEX = "document_tenant_source"
CHUNK_TENANT_DOCUMENT_INDEX = "chunk_tenant_document"


class InMemoryKnowledgeCollection:
    """In-process collection implementing the knowledge collection surface."""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    async def find_one(self, filter: dict[str, Any]) -> dict[str, Any] | None:
        return next(
            (document for document in self._documents.values() if _matches(document, filter)),
            None,
        )

    async def find(self, filter: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            document
            for document in self._documents.values()
            if _matches(document, filter)
        ]

    async def insert_one(self, document: dict[str, Any]) -> None:
        document_id = document["_id"]
        if document_id in self._documents:
            raise ValueError(f"Document with _id '{document_id}' already exists.")
        self._documents[document_id] = dict(document)

    async def update_one(
        self, filter: dict[str, Any], update: dict[str, Any], *, upsert: bool = False
    ) -> None:
        document = await self.find_one(filter)
        if document is None:
            if upsert:
                created = _upsert_document(filter, update)
                self._documents[created["_id"]] = created
            return
        document.update(update.get("$set", {}))

    async def delete_many(self, filter: dict[str, Any]) -> int:
        remaining = {
            document_id: document
            for document_id, document in self._documents.items()
            if not _matches(document, filter)
        }
        deleted = len(self._documents) - len(remaining)
        self._documents = remaining
        return deleted

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str:
        return str(kwargs.get("name", ""))


def _matches(document: dict[str, Any], filter: dict[str, Any]) -> bool:
    for key, expected in filter.items():
        value = document.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


def _upsert_document(
    filter: dict[str, Any], update: dict[str, Any]
) -> dict[str, Any]:
    document: dict[str, Any] = {
        key: value
        for key, value in filter.items()
        if not isinstance(value, dict)
    }
    document.update(update.get("$setOnInsert", {}))
    document.update(update.get("$set", {}))
    if "_id" not in document:
        raise ValueError("Upsert requires an _id in the filter.")
    return document


class MongoKnowledgeCollection:
    """Adapt a real MongoDB collection to the minimal knowledge surface."""

    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def find_one(self, filter: dict[str, Any]) -> dict[str, Any] | None:
        return await self._collection.find_one(filter)

    async def find(self, filter: dict[str, Any]) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        async for document in self._collection.find(filter):
            documents.append(document)
        return documents

    async def insert_one(self, document: dict[str, Any]) -> None:
        await self._collection.insert_one(document)

    async def update_one(
        self, filter: dict[str, Any], update: dict[str, Any], *, upsert: bool = False
    ) -> None:
        await self._collection.update_one(filter, update, upsert=upsert)

    async def delete_many(self, filter: dict[str, Any]) -> int:
        result = await self._collection.delete_many(filter)
        return result.deleted_count

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str:
        return await self._collection.create_index(keys, **kwargs)


class InMemoryKnowledgeCollections:
    """Development collection surface with no external dependencies."""

    def __init__(self) -> None:
        self._collections: dict[str, InMemoryKnowledgeCollection] = {
            KNOWLEDGE_SOURCES_COLLECTION: InMemoryKnowledgeCollection(),
            KNOWLEDGE_DOCUMENTS_COLLECTION: InMemoryKnowledgeCollection(),
            KNOWLEDGE_CHUNKS_COLLECTION: InMemoryKnowledgeCollection(),
        }

    def __getitem__(self, name: str) -> InMemoryKnowledgeCollection:
        return self._collections[name]

    async def close(self) -> None:
        return None


class MongoKnowledgeCollections:
    """MongoDB-backed collection surface for knowledge domain data."""

    def __init__(self, *, mongodb_url: str, database_name: str) -> None:
        self._client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=1_000)
        self._database = self._client[database_name]

    def __getitem__(self, name: str) -> MongoKnowledgeCollection:
        return MongoKnowledgeCollection(self._database[name])

    async def close(self) -> None:
        await self._client.close()


class KnowledgeDatabase:
    """Compose knowledge persistence boundaries and application services."""

    def __init__(
        self,
        *,
        collections: KnowledgeCollectionDatabase,
        embedder: EmbeddingProvider | None = None,
        agent_sources: AgentKnowledgeResolver | None = None,
    ) -> None:
        self._collections = collections
        self._embedder = embedder or MockEmbeddingProvider()
        self._agent_sources = agent_sources or MappingAgentKnowledgeResolver()

        self.source_service = KnowledgeSourceService(
            KnowledgeSourceRepository(collections)
        )
        self.document_service = KnowledgeDocumentService(
            KnowledgeDocumentRepository(collections), self.source_service
        )
        chunks = CollectionVectorRepository(collections[KNOWLEDGE_CHUNKS_COLLECTION])
        self.ingestion_service = KnowledgeIngestionService(
            documents=self.document_service,
            embedder=self._embedder,
            repository=chunks,
        )
        self.retriever = KnowledgeRetrieverService(
            sources=self._agent_sources,
            documents=self.document_service,
            embedder=self._embedder,
            repository=chunks,
        )
        self.search_service = KnowledgeSearchService(self.retriever)

    async def initialize(self) -> None:
        """Create the tenant-scoped indexes for knowledge collections."""
        await self._collections[KNOWLEDGE_SOURCES_COLLECTION].create_index(
            [("tenant_id", 1)], name=SOURCE_TENANT_INDEX
        )
        await self._collections[KNOWLEDGE_DOCUMENTS_COLLECTION].create_index(
            [("tenant_id", 1), ("source_id", 1)], name=DOCUMENT_TENANT_SOURCE_INDEX
        )
        await self._collections[KNOWLEDGE_CHUNKS_COLLECTION].create_index(
            [("tenant_id", 1), ("document_id", 1)], name=CHUNK_TENANT_DOCUMENT_INDEX
        )

    async def close(self) -> None:
        """Release the underlying persistence connection during shutdown."""
        await self._collections.close()


def create_in_memory_database(
    *,
    embedder: EmbeddingProvider | None = None,
    agent_sources: AgentKnowledgeResolver | None = None,
) -> KnowledgeDatabase:
    """Build the development knowledge stack with no external dependencies."""
    return KnowledgeDatabase(
        collections=InMemoryKnowledgeCollections(),
        embedder=embedder,
        agent_sources=agent_sources,
    )


def create_knowledge_database(
    *,
    embedder: EmbeddingProvider | None = None,
    agent_sources: AgentKnowledgeResolver | None = None,
) -> KnowledgeDatabase:
    """Build the production knowledge stack from the service configuration."""
    return KnowledgeDatabase(
        collections=MongoKnowledgeCollections(
            mongodb_url=os.getenv(MONGODB_URL_ENV_VAR, "mongodb://localhost:27017"),
            database_name=os.getenv(
                KNOWLEDGE_DATABASE_ENV_VAR, DEFAULT_KNOWLEDGE_DATABASE
            ),
        ),
        embedder=embedder,
        agent_sources=agent_sources,
    )
