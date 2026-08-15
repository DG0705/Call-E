"""Application services for knowledge ingestion and retrieval."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel

from call_e_shared.exceptions import PlatformError
from knowledge_service.chunking import ChunkingConfig, chunk_text, normalize_text
from knowledge_service.embeddings import EmbeddingProvider
from knowledge_service.models import (
    KnowledgeDocument,
    KnowledgeSource,
    SourceType,
)
from knowledge_service.repositories import (
    KnowledgeDocumentRepository,
    KnowledgeSourceRepository,
)
from knowledge_service.retrieval import (
    KnowledgeRetriever,
    RetrievedChunk,
)
from knowledge_service.storage import StoredChunk, VectorRepository


class IngestionResult(BaseModel):
    """Outcome of ingesting one knowledge document."""

    document_id: str
    tenant_id: str
    chunks: int


class KnowledgeSourceService:
    """Application boundary for tenant knowledge sources."""

    def __init__(self, repository: KnowledgeSourceRepository) -> None:
        self._repository = repository

    async def create_source(
        self,
        *,
        tenant_id: str,
        name: str,
        description: str = "",
        source_type: SourceType = "text",
    ) -> KnowledgeSource:
        now = datetime.now(UTC)
        source = KnowledgeSource(
            id=uuid4().hex,
            tenant_id=tenant_id,
            name=name,
            description=description,
            source_type=source_type,
            created_at=now,
            updated_at=now,
        )
        await self._repository.create(source)
        return source

    async def get_source(self, *, tenant_id: str, source_id: str) -> KnowledgeSource:
        source = await self._repository.get_by_tenant_and_id(
            tenant_id=tenant_id, source_id=source_id
        )
        if source is None:
            raise PlatformError(
                code="knowledge_source_not_found",
                message="Knowledge source was not found.",
                status_code=404,
            )
        return source

    async def list_sources(self, *, tenant_id: str) -> list[KnowledgeSource]:
        return await self._repository.list_by_tenant(tenant_id=tenant_id)


class KnowledgeDocumentService:
    """Application boundary for tenant knowledge documents."""

    def __init__(
        self,
        repository: KnowledgeDocumentRepository,
        sources: KnowledgeSourceService,
    ) -> None:
        self._repository = repository
        self._sources = sources

    async def create_document(
        self,
        *,
        tenant_id: str,
        source_id: str,
        title: str,
        source_type: SourceType = "text",
        raw_content: str,
    ) -> KnowledgeDocument:
        await self._sources.get_source(tenant_id=tenant_id, source_id=source_id)
        now = datetime.now(UTC)
        document = KnowledgeDocument(
            id=uuid4().hex,
            tenant_id=tenant_id,
            source_id=source_id,
            title=title,
            source_type=source_type,
            raw_content=raw_content,
            created_at=now,
            updated_at=now,
        )
        await self._repository.create(document)
        return document

    async def get_document(
        self, *, tenant_id: str, document_id: str
    ) -> KnowledgeDocument:
        document = await self._repository.get_by_tenant_and_id(
            tenant_id=tenant_id, document_id=document_id
        )
        if document is None:
            raise PlatformError(
                code="knowledge_document_not_found",
                message="Knowledge document was not found.",
                status_code=404,
            )
        return document

    async def list_documents(self, *, tenant_id: str) -> list[KnowledgeDocument]:
        return await self._repository.list_by_tenant(tenant_id=tenant_id)

    async def list_by_tenant_and_sources(
        self, *, tenant_id: str, source_ids: list[str]
    ) -> list[KnowledgeDocument]:
        return await self._repository.list_by_tenant_and_sources(
            tenant_id=tenant_id, source_ids=source_ids
        )


class KnowledgeIngestionService:
    """Normalize, chunk, embed, and store one knowledge document."""

    def __init__(
        self,
        *,
        documents: KnowledgeDocumentService,
        embedder: EmbeddingProvider,
        repository: VectorRepository,
        chunking: ChunkingConfig | None = None,
    ) -> None:
        self._documents = documents
        self._embedder = embedder
        self._repository = repository
        self._chunking = chunking or ChunkingConfig()

    async def ingest_document(
        self, *, tenant_id: str, document_id: str
    ) -> IngestionResult:
        document = await self._documents.get_document(
            tenant_id=tenant_id, document_id=document_id
        )
        normalized = normalize_text(document.raw_content, source_type=document.source_type)
        chunks = chunk_text(normalized, config=self._chunking)
        await self._repository.delete_document(
            tenant_id=tenant_id, document_id=document_id
        )
        for index, content in enumerate(chunks):
            embedding = await self._embedder.embed_text(content)
            await self._repository.save_chunk(
                StoredChunk(
                    document_id=document.id,
                    chunk_id=f"{document.id}:{index}",
                    tenant_id=document.tenant_id,
                    source_id=document.source_id,
                    index=index,
                    content=content,
                    vector=embedding.vector,
                    embedding_model=str(embedding.usage.get("model", "")),
                )
            )
        return IngestionResult(
            document_id=document.id,
            tenant_id=document.tenant_id,
            chunks=len(chunks),
        )


class KnowledgeSearchService:
    """Application boundary for tenant- and agent-scoped knowledge search."""

    def __init__(self, retriever: KnowledgeRetriever) -> None:
        self._retriever = retriever

    async def search(
        self, *, tenant_id: str, agent_id: str, query: str, top_k: int = 3
    ) -> list[RetrievedChunk]:
        return await self._retriever.retrieve(
            tenant_id=tenant_id,
            agent_id=agent_id,
            query=query,
            top_k=top_k,
        )
