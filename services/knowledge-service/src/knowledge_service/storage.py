"""Vector storage abstraction with a collection-backed cosine implementation."""

from math import sqrt
from typing import Any, Protocol

from pydantic import BaseModel

from knowledge_service.repositories import KnowledgeCollectionSurface


class StoredChunk(BaseModel):
    """An embedded knowledge chunk persisted for retrieval."""

    document_id: str
    chunk_id: str
    tenant_id: str
    source_id: str
    index: int
    content: str
    vector: list[float]
    embedding_model: str


class ChunkMatch(BaseModel):
    """A scored knowledge chunk returned by a vector search."""

    chunk_id: str
    document_id: str
    tenant_id: str
    score: float
    content: str


class VectorRepository(Protocol):
    """Persistence boundary for embedded knowledge chunks."""

    async def save_chunk(self, chunk: StoredChunk) -> None: ...

    async def delete_document(self, *, tenant_id: str, document_id: str) -> int: ...

    async def search(
        self,
        *,
        tenant_id: str,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[ChunkMatch]: ...


class CollectionVectorRepository:
    """Embedded chunk persistence with in-process cosine similarity search."""

    def __init__(self, collection: KnowledgeCollectionSurface) -> None:
        self._collection = collection

    async def save_chunk(self, chunk: StoredChunk) -> None:
        """Upsert an embedded chunk under its deterministic chunk identifier."""
        await self._collection.update_one(
            {"_id": chunk.chunk_id, "tenant_id": chunk.tenant_id},
            {
                "$set": {
                    "document_id": chunk.document_id,
                    "source_id": chunk.source_id,
                    "index": chunk.index,
                    "content": chunk.content,
                    "vector": chunk.vector,
                    "embedding_model": chunk.embedding_model,
                }
            },
            upsert=True,
        )

    async def delete_document(self, *, tenant_id: str, document_id: str) -> int:
        """Remove all embedded chunks for one document within its tenant."""
        return await self._collection.delete_many(
            {"tenant_id": tenant_id, "document_id": document_id}
        )

    async def search(
        self,
        *,
        tenant_id: str,
        vector: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[ChunkMatch]:
        """Return the top-k most similar chunks, always scoped to a tenant."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if document_ids:
            query["document_id"] = {"$in": document_ids}
        matches: list[ChunkMatch] = []
        for document in await self._collection.find(query):
            chunk_vector = document.get("vector") or []
            if not chunk_vector:
                continue
            matches.append(
                ChunkMatch(
                    chunk_id=document["_id"],
                    document_id=document["document_id"],
                    tenant_id=document["tenant_id"],
                    score=_cosine_similarity(vector, chunk_vector),
                    content=document.get("content", ""),
                )
            )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(left * right for left, right in zip(a, b))
    norm_a = sqrt(sum(value * value for value in a))
    norm_b = sqrt(sum(value * value for value in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
