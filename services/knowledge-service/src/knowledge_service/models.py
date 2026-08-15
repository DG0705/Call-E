"""Knowledge domain persistence models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


KNOWLEDGE_SOURCES_COLLECTION = "knowledge_sources"
KNOWLEDGE_DOCUMENTS_COLLECTION = "knowledge_documents"
KNOWLEDGE_CHUNKS_COLLECTION = "knowledge_chunks"

SourceType = Literal["text", "markdown", "html", "pdf"]


class KnowledgeSource(BaseModel):
    """A tenant-scoped grouping of knowledge documents."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    tenant_id: str
    name: str
    description: str = ""
    source_type: SourceType = "text"
    status: str = "active"
    created_at: datetime
    updated_at: datetime


class KnowledgeDocument(BaseModel):
    """One tenant-scoped document belonging to a knowledge source."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    tenant_id: str
    source_id: str
    title: str
    source_type: SourceType = "text"
    raw_content: str
    status: str = "active"
    created_at: datetime
    updated_at: datetime


class KnowledgeChunk(BaseModel):
    """A normalized, indexable slice of a knowledge document."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    tenant_id: str
    document_id: str
    source_id: str
    index: int
    content: str
    created_at: datetime
