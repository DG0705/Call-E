"""Knowledge ingestion and retrieval routes."""

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field

from knowledge_service.models import (
    KnowledgeDocument,
    KnowledgeSource,
    SourceType,
)
from knowledge_service.retrieval import RetrievedChunk
from knowledge_service.services import UploadedFile, UploadFileResult


router = APIRouter(tags=["knowledge"])


class CreateSourceRequest(BaseModel):
    """Input accepted when creating a knowledge source."""

    tenant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    source_type: SourceType = "text"


class CreateDocumentRequest(BaseModel):
    """Input accepted when creating a knowledge document."""

    tenant_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: SourceType = "text"
    raw_content: str


class IngestDocumentRequest(BaseModel):
    """Input accepted when ingesting a knowledge document."""

    tenant_id: str = Field(min_length=1)


class IngestDocumentResponse(BaseModel):
    """Stable response for a completed document ingestion."""

    document_id: str
    tenant_id: str
    chunks: int
    request_id: str | None = None


class SearchRequest(BaseModel):
    """Input accepted by the tenant- and agent-scoped knowledge search."""

    tenant_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    source_ids: list[str] | None = None


class WebsiteIngestRequest(BaseModel):
    """Input accepted when ingesting a single website page."""

    tenant_id: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=2048)
    name: str | None = None


class UploadResponse(BaseModel):
    """Per-file upload outcomes for one upload request."""

    files: list[UploadFileResult]


class SearchResponse(BaseModel):
    """Stable response for a knowledge search."""

    tenant_id: str
    agent_id: str
    query: str
    results: list[RetrievedChunk]
    request_id: str | None = None


@router.post(
    "/api/v1/knowledge/sources",
    response_model=KnowledgeSource,
    response_model_by_alias=False,
)
async def create_source(
    request: Request, payload: CreateSourceRequest
) -> KnowledgeSource:
    """Create a tenant-scoped knowledge source."""
    return await request.app.state.source_service.create_source(
        tenant_id=payload.tenant_id,
        name=payload.name,
        description=payload.description,
        source_type=payload.source_type,
    )


@router.get(
    "/api/v1/knowledge/sources",
    response_model=list[KnowledgeSource],
    response_model_by_alias=False,
)
async def list_sources(
    request: Request, tenant_id: str = Query(min_length=1)
) -> list[KnowledgeSource]:
    """List knowledge sources visible to one tenant."""
    return await request.app.state.source_service.list_sources(tenant_id=tenant_id)


@router.post(
    "/api/v1/knowledge/documents",
    response_model=KnowledgeDocument,
    response_model_by_alias=False,
)
async def create_document(
    request: Request, payload: CreateDocumentRequest
) -> KnowledgeDocument:
    """Create a tenant-scoped knowledge document inside an existing source."""
    return await request.app.state.document_service.create_document(
        tenant_id=payload.tenant_id,
        source_id=payload.source_id,
        title=payload.title,
        source_type=payload.source_type,
        raw_content=payload.raw_content,
    )


@router.get(
    "/api/v1/knowledge/documents",
    response_model=list[KnowledgeDocument],
    response_model_by_alias=False,
)
async def list_documents(
    request: Request, tenant_id: str = Query(min_length=1)
) -> list[KnowledgeDocument]:
    """List knowledge documents visible to one tenant."""
    return await request.app.state.document_service.list_documents(tenant_id=tenant_id)


@router.post(
    "/api/v1/knowledge/documents/{document_id}/ingest",
    response_model=IngestDocumentResponse,
)
async def ingest_document(
    request: Request, document_id: str, payload: IngestDocumentRequest
) -> IngestDocumentResponse:
    """Normalize, chunk, embed, and store one knowledge document."""
    result = await request.app.state.ingestion_service.ingest_document(
        tenant_id=payload.tenant_id, document_id=document_id
    )
    return IngestDocumentResponse(
        document_id=result.document_id,
        tenant_id=result.tenant_id,
        chunks=result.chunks,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/api/v1/knowledge/search", response_model=SearchResponse)
async def search_knowledge(request: Request, payload: SearchRequest) -> SearchResponse:
    """Return knowledge chunks scoped to one tenant and agent."""
    results = await request.app.state.search_service.search(
        tenant_id=payload.tenant_id,
        agent_id=payload.agent_id,
        query=payload.query,
        top_k=payload.top_k,
        source_ids=payload.source_ids,
    )
    return SearchResponse(
        tenant_id=payload.tenant_id,
        agent_id=payload.agent_id,
        query=payload.query,
        results=results,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/api/v1/knowledge/sources/{source_id}",
    response_model=KnowledgeSource,
    response_model_by_alias=False,
)
async def get_source(
    request: Request, source_id: str, tenant_id: str = Query(min_length=1)
) -> KnowledgeSource:
    """Return one tenant-scoped knowledge source with its ingestion state."""
    return await request.app.state.source_service.get_source(
        tenant_id=tenant_id, source_id=source_id
    )


@router.get(
    "/api/v1/knowledge/documents/{document_id}",
    response_model=KnowledgeDocument,
    response_model_by_alias=False,
)
async def get_document(
    request: Request, document_id: str, tenant_id: str = Query(min_length=1)
) -> KnowledgeDocument:
    """Return one tenant-scoped knowledge document with its ingestion state."""
    return await request.app.state.document_service.get_document(
        tenant_id=tenant_id, document_id=document_id
    )


@router.post(
    "/api/v1/knowledge/uploads",
    response_model=UploadResponse,
)
async def upload_files(
    request: Request,
    tenant_id: str = Form(min_length=1),
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    """Upload customer files and ingest each one; per-file results returned."""
    uploads: list[UploadedFile] = []
    for upload in files:
        content = await upload.read()
        uploads.append(
            UploadedFile(
                filename=upload.filename or "upload",
                content_type=upload.content_type,
                size_bytes=len(content),
                content=content,
            )
        )
    results = await request.app.state.upload_service.upload_files(
        tenant_id=tenant_id, files=uploads
    )
    return UploadResponse(files=results)


@router.post(
    "/api/v1/knowledge/websites",
    response_model=KnowledgeDocument,
    response_model_by_alias=False,
)
async def ingest_website(
    request: Request, payload: WebsiteIngestRequest
) -> KnowledgeDocument:
    """Fetch one website page and ingest it as a knowledge document."""
    return await request.app.state.upload_service.ingest_website(
        tenant_id=payload.tenant_id, url=payload.url, name=payload.name
    )
