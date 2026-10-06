"""Application services for knowledge ingestion and retrieval."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel

from call_e_shared.exceptions import PlatformError
from knowledge_service.chunking import ChunkingConfig, chunk_text, normalize_text
from knowledge_service.embeddings import EmbeddingProvider, EmbeddingResult
from knowledge_service.extraction import (
    ExtractedText,
    ExtractionError,
    extract_text,
    is_supported,
)
from knowledge_service.files import FileStorage
from knowledge_service.website import FetchError, HttpxWebsiteFetcher
from knowledge_service.models import (
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PROCESSING,
    DOCUMENT_STATUS_READY,
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


logger = logging.getLogger("knowledge_service.ingestion")

# Upper bound on texts sent to a real embedding provider in one request.
# Bounding keeps a large document from producing one oversized request while
# still avoiding a separate network call per chunk.
DEFAULT_EMBEDDING_BATCH_SIZE = 64


def _ingestion_error_detail(exc: Exception) -> str:
    """Return a short, secret-free cause for a failed document.

    PlatformError carries a user-safe message; anything else is reduced to its
    type and message so the UI and logs show why ingestion failed instead of a
    blank 'unexpected' string. Provider errors never embed credentials.
    """
    if isinstance(exc, PlatformError):
        return exc.message
    detail = str(exc).strip()
    text = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    return text[:300]


class IngestionResult(BaseModel):
    """Outcome of ingesting one knowledge document."""

    document_id: str
    tenant_id: str
    chunks: int


class KnowledgeSourceService:
    """Application boundary for tenant knowledge sources."""

    def __init__(
        self,
        repository: KnowledgeSourceRepository,
        documents: KnowledgeDocumentRepository | None = None,
        chunks: VectorRepository | None = None,
    ) -> None:
        self._repository = repository
        self._documents = documents
        self._chunks = chunks

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

    async def delete_source(self, *, tenant_id: str, source_id: str) -> None:
        """Delete one source with its documents and embedded chunks.

        Tenant-scoped: a missing or cross-tenant source resolves to None and
        raises 404, so one tenant can never delete another tenant's data.
        Attached agents keep their configuration; the dangling source id is
        simply skipped at retrieval time.
        """
        await self.get_source(tenant_id=tenant_id, source_id=source_id)
        if self._chunks is not None:
            await self._chunks.delete_source(tenant_id=tenant_id, source_id=source_id)
        if self._documents is not None:
            await self._documents.delete_by_source(
                tenant_id=tenant_id, source_id=source_id
            )
        await self._repository.delete(tenant_id=tenant_id, source_id=source_id)


class KnowledgeDocumentService:
    """Application boundary for tenant knowledge documents."""

    def __init__(
        self,
        repository: KnowledgeDocumentRepository,
        sources: KnowledgeSourceService,
        chunks: VectorRepository | None = None,
    ) -> None:
        self._repository = repository
        self._sources = sources
        self._chunks = chunks

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

    async def save_document(self, document: KnowledgeDocument) -> None:
        """Persist document state (status, chunks, error) in place."""
        document.updated_at = datetime.now(UTC)
        await self._repository.save(document)

    async def store_document(self, document: KnowledgeDocument) -> None:
        """Persist a pre-built document (used by upload/website flows)."""
        await self._repository.create(document)

    async def list_documents(self, *, tenant_id: str) -> list[KnowledgeDocument]:
        return await self._repository.list_by_tenant(tenant_id=tenant_id)

    async def list_by_tenant_and_sources(
        self, *, tenant_id: str, source_ids: list[str]
    ) -> list[KnowledgeDocument]:
        return await self._repository.list_by_tenant_and_sources(
            tenant_id=tenant_id, source_ids=source_ids
        )

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        """Delete one document and its embedded chunks, scoped to its tenant."""
        await self.get_document(tenant_id=tenant_id, document_id=document_id)
        if self._chunks is not None:
            await self._chunks.delete_document(
                tenant_id=tenant_id, document_id=document_id
            )
        await self._repository.delete(tenant_id=tenant_id, document_id=document_id)


class KnowledgeIngestionService:
    """Normalize, chunk, embed, and store one knowledge document."""

    def __init__(
        self,
        *,
        documents: KnowledgeDocumentService,
        embedder: EmbeddingProvider,
        repository: VectorRepository,
        chunking: ChunkingConfig | None = None,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1.")
        self._documents = documents
        self._embedder = embedder
        self._repository = repository
        self._chunking = chunking or ChunkingConfig()
        self._batch_size = batch_size

    async def _embed_chunks(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed chunk texts in bounded batches, preserving input order.

        Each batch is one provider request; results are concatenated in order
        so ``embeddings[i]`` always corresponds to ``texts[i]``.
        """
        results: list[EmbeddingResult] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            results.extend(await self._embedder.embed_texts(batch))
        return results

    async def ingest_document(
        self, *, tenant_id: str, document_id: str
    ) -> IngestionResult:
        document = await self._documents.get_document(
            tenant_id=tenant_id, document_id=document_id
        )
        document.status = DOCUMENT_STATUS_PROCESSING
        document.error = None
        await self._documents.save_document(document)
        try:
            normalized = normalize_text(
                document.raw_content, source_type=document.source_type
            )
            chunks = chunk_text(normalized, config=self._chunking)
            if not chunks:
                raise PlatformError(
                    code="knowledge_document_empty",
                    message="Document produced no indexable text.",
                    status_code=422,
                )
            # Authoritative re-ingestion: stale chunks are removed before the
            # new ones persist, so one document never mixes old and new text.
            await self._repository.delete_document(
                tenant_id=tenant_id, document_id=document_id
            )
            embeddings = await self._embed_chunks(chunks)
            for index, (content, embedding) in enumerate(
                zip(chunks, embeddings, strict=True)
            ):
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
        except Exception as exc:
            document.status = DOCUMENT_STATUS_FAILED
            document.error = _ingestion_error_detail(exc)
            logger.warning(
                "INGESTION_FAILED document_id=%s tenant_id=%s cause=%r",
                document.id,
                document.tenant_id,
                exc,
            )
            await self._documents.save_document(document)
            raise
        document.status = DOCUMENT_STATUS_READY
        document.error = None
        document.chunks = len(chunks)
        await self._documents.save_document(document)
        return IngestionResult(
            document_id=document.id,
            tenant_id=document.tenant_id,
            chunks=len(chunks),
        )

    async def ingest_extracted_text(
        self,
        *,
        tenant_id: str,
        source_id: str,
        title: str,
        extracted: ExtractedText,
        file_name: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        source_url: str | None = None,
    ) -> KnowledgeDocument:
        """Create a document from extracted text and ingest it synchronously.

        Used by file-upload and website flows: the caller already extracted
        readable text, so this method owns create → ingest → ready/failed
        with the document status persisted at every step.
        """
        now = datetime.now(UTC)
        source_type: SourceType = (
            extracted.source_type
            if extracted.source_type in ("text", "markdown", "html", "pdf")
            else "text"
        )
        document = KnowledgeDocument(
            id=uuid4().hex,
            tenant_id=tenant_id,
            source_id=source_id,
            title=title,
            source_type=source_type,
            raw_content=extracted.text,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            source_url=source_url,
            created_at=now,
            updated_at=now,
        )
        await self._documents.store_document(document)
        try:
            if extracted.table_rows:
                await self.ingest_table_rows(
                    document=document, rows=extracted.table_rows
                )
            else:
                await self.ingest_document(
                    tenant_id=tenant_id, document_id=document.id
                )
        except Exception as exc:
            # The document is already persisted with status=failed and the real
            # cause by ingest_document/ingest_table_rows. Log it here so the
            # failure is never silent, then return the failed document so the
            # upload/website flow reports it honestly instead of raising a 500.
            logger.error(
                "INGESTION_ERROR document_id=%s tenant_id=%s title=%r cause=%r",
                document.id,
                tenant_id,
                title,
                exc,
            )
        return await self._documents.get_document(
            tenant_id=tenant_id, document_id=document.id
        )

    async def ingest_table_rows(
        self, *, document: KnowledgeDocument, rows: list[str]
    ) -> IngestionResult:
        """Index one chunk per table row for row-granular recall.

        Tabular facts (prices, sizes) retrieve far better as individual
        row chunks than as one diluted table blob. Chunk identity stays
        ``{document_id}:{index}`` so re-ingestion replaces stale rows
        deterministically, exactly like the generic path.
        """
        document.status = DOCUMENT_STATUS_PROCESSING
        document.error = None
        await self._documents.save_document(document)
        try:
            blocks: list[str] = []
            for row in rows:
                normalized = normalize_text(row, source_type="text")
                if not normalized:
                    continue
                if len(normalized) > self._chunking.chunk_size:
                    blocks.extend(
                        chunk_text(normalized, config=self._chunking)
                    )
                else:
                    blocks.append(normalized)
            if not blocks:
                raise PlatformError(
                    code="knowledge_document_empty",
                    message="Document produced no indexable text.",
                    status_code=422,
                )
            await self._repository.delete_document(
                tenant_id=document.tenant_id, document_id=document.id
            )
            embeddings = await self._embed_chunks(blocks)
            for index, (content, embedding) in enumerate(
                zip(blocks, embeddings, strict=True)
            ):
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
        except Exception as exc:
            document.status = DOCUMENT_STATUS_FAILED
            document.error = _ingestion_error_detail(exc)
            logger.warning(
                "INGESTION_FAILED document_id=%s tenant_id=%s cause=%r",
                document.id,
                document.tenant_id,
                exc,
            )
            await self._documents.save_document(document)
            raise
        document.status = DOCUMENT_STATUS_READY
        document.error = None
        document.chunks = len(blocks)
        await self._documents.save_document(document)
        return IngestionResult(
            document_id=document.id,
            tenant_id=document.tenant_id,
            chunks=len(blocks),
        )


class KnowledgeSearchService:
    """Application boundary for tenant- and agent-scoped knowledge search."""

    def __init__(self, retriever: KnowledgeRetriever) -> None:
        self._retriever = retriever

    async def search(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        query: str,
        top_k: int = 3,
        source_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return await self._retriever.retrieve(
            tenant_id=tenant_id,
            agent_id=agent_id,
            query=query,
            top_k=top_k,
            source_ids=source_ids,
        )


class UploadFileResult(BaseModel):
    """Per-file outcome of a knowledge upload request."""

    file_name: str
    source_id: str | None = None
    document_id: str | None = None
    status: str = DOCUMENT_STATUS_FAILED
    chunks: int = 0
    error: str | None = None


class UploadedFile(BaseModel):
    """Validated upload bytes decoupled from the HTTP layer."""

    filename: str
    content_type: str | None = None
    size_bytes: int = 0
    content: bytes = b""


class KnowledgeUploadService:
    """Tenant-scoped file-upload and website ingestion orchestration."""

    def __init__(
        self,
        *,
        sources: KnowledgeSourceService,
        documents: KnowledgeDocumentService,
        ingestion: KnowledgeIngestionService,
        storage: FileStorage,
        max_file_bytes: int = 10_000_000,
        max_files_per_request: int = 10,
    ) -> None:
        self._sources = sources
        self._documents = documents
        self._ingestion = ingestion
        self._storage = storage
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files_per_request

    async def upload_files(
        self,
        *,
        tenant_id: str,
        files: list[UploadedFile],
    ) -> list[UploadFileResult]:
        """Validate, store, extract, and ingest each uploaded file."""
        if not files:
            raise PlatformError(
                code="knowledge_upload_empty",
                message="No files were uploaded.",
                status_code=422,
            )
        if len(files) > self._max_files:
            raise PlatformError(
                code="knowledge_upload_too_many",
                message=f"At most {self._max_files} files per request.",
                status_code=422,
            )
        return [
            await self._upload_one(tenant_id=tenant_id, upload=file)
            for file in files
        ]

    async def _upload_one(
        self, *, tenant_id: str, upload: UploadedFile
    ) -> UploadFileResult:
        file_name = (upload.filename or "").strip() or "upload"
        if not is_supported(file_name, upload.content_type):
            return UploadFileResult(
                file_name=file_name,
                error=f"Unsupported file type for '{file_name}'.",
            )
        if upload.size_bytes > self._max_file_bytes:
            limit_mb = self._max_file_bytes // 1_000_000
            return UploadFileResult(
                file_name=file_name,
                error=f"'{file_name}' exceeds the {limit_mb} MB upload limit.",
            )
        try:
            extracted = extract_text(
                upload.content,
                filename=file_name,
                mime_type=upload.content_type,
            )
        except ExtractionError as exc:
            source = await self._sources.create_source(
                tenant_id=tenant_id,
                name=file_name,
                description=f"Uploaded file {file_name}",
                source_type="text",
            )
            document = await self._failed_document(
                tenant_id=tenant_id,
                source_id=source.id,
                title=file_name,
                file_name=file_name,
                mime_type=upload.content_type,
                size_bytes=upload.size_bytes,
                error=str(exc),
            )
            return UploadFileResult(
                file_name=file_name,
                source_id=source.id,
                document_id=document.id,
                status=document.status,
                error=document.error,
            )
        storage_key = await self._storage.save(
            tenant_id=tenant_id, filename=file_name, content=upload.content
        )
        _ = storage_key
        source = await self._sources.create_source(
            tenant_id=tenant_id,
            name=file_name,
            description=f"Uploaded file {file_name}",
            source_type=extracted.source_type,  # type: ignore[arg-type]
        )
        document = await self._ingestion.ingest_extracted_text(
            tenant_id=tenant_id,
            source_id=source.id,
            title=extracted.title,
            extracted=extracted,
            file_name=file_name,
            mime_type=upload.content_type,
            size_bytes=upload.size_bytes,
        )
        return UploadFileResult(
            file_name=file_name,
            source_id=source.id,
            document_id=document.id,
            status=document.status,
            chunks=document.chunks,
            error=document.error,
        )

    async def _failed_document(
        self,
        *,
        tenant_id: str,
        source_id: str,
        title: str,
        file_name: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        source_url: str | None = None,
        error: str,
    ) -> KnowledgeDocument:
        """Persist an honestly-failed document so the UI can show the error."""
        now = datetime.now(UTC)
        document = KnowledgeDocument(
            id=uuid4().hex,
            tenant_id=tenant_id,
            source_id=source_id,
            title=title,
            source_type="text",
            raw_content="",
            status=DOCUMENT_STATUS_FAILED,
            error=error,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            source_url=source_url,
            created_at=now,
            updated_at=now,
        )
        await self._documents.store_document(document)
        return document

    async def ingest_website(
        self,
        *,
        tenant_id: str,
        url: str,
        name: str | None,
        fetcher: HttpxWebsiteFetcher | None = None,
    ) -> KnowledgeDocument:
        """Fetch one website page and ingest it as a document."""
        try:
            page = await (fetcher or HttpxWebsiteFetcher()).fetch_page(url)
        except FetchError as exc:
            raise PlatformError(
                code="knowledge_website_fetch_failed",
                message=str(exc),
                status_code=422,
            ) from exc
        source = await self._sources.create_source(
            tenant_id=tenant_id,
            name=name or page.title,
            description=f"Website page {page.url}",
            source_type="text",
        )
        extracted = ExtractedText(
            text=page.text, title=page.title, source_type="text"
        )
        return await self._ingestion.ingest_extracted_text(
            tenant_id=tenant_id,
            source_id=source.id,
            title=page.title,
            extracted=extracted,
            source_url=page.url,
        )
