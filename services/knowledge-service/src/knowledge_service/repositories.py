"""Persistence boundaries for knowledge domain data."""

from typing import Any, Protocol

from knowledge_service.models import (
    KNOWLEDGE_DOCUMENTS_COLLECTION,
    KNOWLEDGE_SOURCES_COLLECTION,
    KnowledgeDocument,
    KnowledgeSource,
)


class KnowledgeCollectionSurface(Protocol):
    """The minimal async collection surface used by knowledge repositories."""

    async def find_one(self, filter: dict[str, Any]) -> dict[str, Any] | None: ...

    async def find(self, filter: dict[str, Any]) -> list[dict[str, Any]]: ...

    async def insert_one(self, document: dict[str, Any]) -> None: ...

    async def update_one(
        self, filter: dict[str, Any], update: dict[str, Any], *, upsert: bool = False
    ) -> None: ...

    async def delete_many(self, filter: dict[str, Any]) -> int: ...

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str: ...


class KnowledgeCollectionDatabase(Protocol):
    """Database surface that resolves named collection surfaces."""

    def __getitem__(self, name: str) -> KnowledgeCollectionSurface: ...

    async def close(self) -> None: ...


class KnowledgeSourceRepository:
    """Access to the tenant-scoped knowledge source collection."""

    def __init__(self, database: KnowledgeCollectionDatabase) -> None:
        self._collection = database[KNOWLEDGE_SOURCES_COLLECTION]

    async def create(self, source: KnowledgeSource) -> None:
        await self._collection.insert_one(source.model_dump(by_alias=True))

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, source_id: str
    ) -> KnowledgeSource | None:
        document = await self._collection.find_one(
            {"_id": source_id, "tenant_id": tenant_id}
        )
        return KnowledgeSource.model_validate(document) if document is not None else None

    async def list_by_tenant(self, *, tenant_id: str) -> list[KnowledgeSource]:
        documents = await self._collection.find({"tenant_id": tenant_id})
        return [KnowledgeSource.model_validate(document) for document in documents]


class KnowledgeDocumentRepository:
    """Access to the tenant-scoped knowledge document collection."""

    def __init__(self, database: KnowledgeCollectionDatabase) -> None:
        self._collection = database[KNOWLEDGE_DOCUMENTS_COLLECTION]

    async def create(self, document: KnowledgeDocument) -> None:
        await self._collection.insert_one(document.model_dump(by_alias=True))

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, document_id: str
    ) -> KnowledgeDocument | None:
        document = await self._collection.find_one(
            {"_id": document_id, "tenant_id": tenant_id}
        )
        return (
            KnowledgeDocument.model_validate(document) if document is not None else None
        )

    async def list_by_tenant(self, *, tenant_id: str) -> list[KnowledgeDocument]:
        documents = await self._collection.find({"tenant_id": tenant_id})
        return [KnowledgeDocument.model_validate(document) for document in documents]

    async def list_by_tenant_and_sources(
        self, *, tenant_id: str, source_ids: list[str]
    ) -> list[KnowledgeDocument]:
        documents = await self._collection.find(
            {"tenant_id": tenant_id, "source_id": {"$in": source_ids}}
        )
        return [KnowledgeDocument.model_validate(document) for document in documents]
