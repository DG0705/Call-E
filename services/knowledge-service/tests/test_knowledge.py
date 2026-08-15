"""Unit tests for knowledge models, chunking, embeddings, and retrieval."""

import asyncio
import math

import pytest

from call_e_shared.exceptions import PlatformError
from knowledge_service.chunking import ChunkingConfig, chunk_text, normalize_text
from knowledge_service.database import (
    InMemoryKnowledgeCollection,
    create_in_memory_database,
)
from knowledge_service.embeddings import MockEmbeddingProvider
from knowledge_service.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
)
from knowledge_service.retrieval import (
    MappingAgentKnowledgeResolver,
    RetrievedChunk,
    build_knowledge_context,
)
from knowledge_service.storage import (
    CollectionVectorRepository,
    StoredChunk,
)


def source_document() -> dict[str, object]:
    return {
        "_id": "source-1",
        "tenant_id": "tenant-1",
        "name": "Support handbook",
        "description": "Customer support reference",
        "source_type": "markdown",
        "created_at": "2026-08-03T12:00:00Z",
        "updated_at": "2026-08-03T12:00:00Z",
    }


def knowledge_document() -> dict[str, object]:
    return {
        "_id": "document-1",
        "tenant_id": "tenant-1",
        "source_id": "source-1",
        "title": "Refund policy",
        "source_type": "text",
        "raw_content": "Customers may request a full refund within 30 days.",
        "created_at": "2026-08-03T12:00:00Z",
        "updated_at": "2026-08-03T12:00:00Z",
    }


def test_knowledge_source_model_serializes_mongo_id() -> None:
    source = KnowledgeSource.model_validate(source_document())

    assert source.id == "source-1"
    assert source.status == "active"
    assert source.model_dump(by_alias=True)["_id"] == "source-1"
    assert source.model_dump()["id"] == "source-1"


def test_knowledge_document_model_is_tenant_and_source_scoped() -> None:
    document = KnowledgeDocument.model_validate(knowledge_document())

    assert document.tenant_id == "tenant-1"
    assert document.source_id == "source-1"
    assert document.model_dump(by_alias=True)["_id"] == "document-1"


def test_knowledge_chunk_has_deterministic_shape() -> None:
    chunk = KnowledgeChunk.model_validate(
        {
            "_id": "document-1:0",
            "tenant_id": "tenant-1",
            "document_id": "document-1",
            "source_id": "source-1",
            "index": 0,
            "content": "Refund policy",
            "created_at": "2026-08-03T12:00:00Z",
        }
    )

    assert chunk.id == "document-1:0"
    assert chunk.content == "Refund policy"
    assert chunk.model_dump(by_alias=True)["_id"] == "document-1:0"


def test_normalize_text_strips_html_and_collapses_whitespace() -> None:
    assert (
        normalize_text("<p>Hello <b>world</b> &amp; co</p>", source_type="html")
        == "Hello world & co"
    )
    assert normalize_text("  line one\n line two  ", source_type="text") == (
        "line one line two"
    )


def test_chunk_text_keeps_short_text_as_single_chunk() -> None:
    assert chunk_text("short content", config=ChunkingConfig()) == ["short content"]


def test_chunk_text_is_deterministic_and_respects_size() -> None:
    text = ("word " * 400).strip()
    first = chunk_text(text, config=ChunkingConfig())
    second = chunk_text(text, config=ChunkingConfig())

    assert first == second
    assert len(first) > 1
    assert all(len(chunk) <= 1000 for chunk in first)
    assert "".join(first).startswith(text[:100])


def test_chunk_text_covers_long_unbroken_text() -> None:
    chunks = chunk_text("a" * 2500, config=ChunkingConfig())

    assert [len(chunk) for chunk in chunks] == [1000, 1000, 900]
    assert "".join(chunks) == "a" * 2900


def test_chunk_text_handles_empty_input() -> None:
    assert chunk_text("", config=ChunkingConfig()) == []
    assert chunk_text("   ", config=ChunkingConfig()) == []


def test_chunking_config_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        ChunkingConfig(chunk_size=100, chunk_overlap=100)


def test_mock_embedding_is_deterministic_and_unit_length() -> None:
    provider = MockEmbeddingProvider()

    first = asyncio.run(provider.embed_text("Refund policy applies"))
    second = asyncio.run(provider.embed_text("Refund policy applies"))

    assert first.vector == second.vector
    assert first.dimensions == 16
    norm = math.sqrt(sum(value * value for value in first.vector))
    assert norm == pytest.approx(1.0)


def test_mock_embedding_ignores_case_and_punctuation() -> None:
    provider = MockEmbeddingProvider()

    punctuated = asyncio.run(provider.embed_text("Refund, policy!"))
    plain = asyncio.run(provider.embed_text("refund policy"))

    assert punctuated.vector == plain.vector


def test_mock_embedding_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError):
        MockEmbeddingProvider(dimensions=0)


async def _store_chunk(
    repository: CollectionVectorRepository,
    *,
    tenant_id: str,
    document_id: str,
    source_id: str,
    content: str,
) -> None:
    embedding = await MockEmbeddingProvider().embed_text(content)
    await repository.save_chunk(
        StoredChunk(
            document_id=document_id,
            chunk_id=f"{document_id}:0",
            tenant_id=tenant_id,
            source_id=source_id,
            index=0,
            content=content,
            vector=embedding.vector,
            embedding_model="test",
        )
    )


def test_vector_repository_scopes_search_by_tenant_and_documents() -> None:
    repository = CollectionVectorRepository(InMemoryKnowledgeCollection())
    asyncio.run(
        _store_chunk(
            repository,
            tenant_id="tenant-1",
            document_id="document-1",
            source_id="source-1",
            content="Refunds are available within 30 days of purchase.",
        )
    )
    asyncio.run(
        _store_chunk(
            repository,
            tenant_id="tenant-2",
            document_id="document-2",
            source_id="source-2",
            content="Refunds are available within 30 days of purchase.",
        )
    )
    query = asyncio.run(MockEmbeddingProvider().embed_text("refund policy"))

    all_hits = asyncio.run(
        repository.search(tenant_id="tenant-1", vector=query.vector, top_k=5)
    )
    scoped_hits = asyncio.run(
        repository.search(
            tenant_id="tenant-1",
            vector=query.vector,
            top_k=5,
            document_ids=["document-1"],
        )
    )
    other_document = asyncio.run(
        repository.search(
            tenant_id="tenant-1",
            vector=query.vector,
            top_k=5,
            document_ids=["document-other"],
        )
    )

    assert [hit.document_id for hit in all_hits] == ["document-1"]
    assert [hit.document_id for hit in scoped_hits] == ["document-1"]
    assert other_document == []
    assert all_hits[0].tenant_id == "tenant-1"


def test_vector_repository_delete_document_removes_chunks() -> None:
    repository = CollectionVectorRepository(InMemoryKnowledgeCollection())
    asyncio.run(
        _store_chunk(
            repository,
            tenant_id="tenant-1",
            document_id="document-1",
            source_id="source-1",
            content="Refunds are available.",
        )
    )
    asyncio.run(
        _store_chunk(
            repository,
            tenant_id="tenant-1",
            document_id="document-2",
            source_id="source-1",
            content="Shipping takes three days.",
        )
    )

    deleted = asyncio.run(
        repository.delete_document(tenant_id="tenant-1", document_id="document-1")
    )
    remaining = asyncio.run(
        repository.search(
            tenant_id="tenant-1",
            vector=[0.1, 0.2],
            top_k=5,
        )
    )

    assert deleted == 1
    assert [hit.document_id for hit in remaining] == ["document-2"]


def test_vector_repository_rejects_invalid_top_k() -> None:
    repository = CollectionVectorRepository(InMemoryKnowledgeCollection())
    with pytest.raises(ValueError):
        asyncio.run(
            repository.search(tenant_id="tenant-1", vector=[0.1], top_k=0)
        )


def test_retriever_returns_nothing_without_agent_sources() -> None:
    database = create_in_memory_database(agent_sources=MappingAgentKnowledgeResolver())
    source = asyncio.run(
        database.source_service.create_source(tenant_id="tenant-1", name="support")
    )
    document = asyncio.run(
        database.document_service.create_document(
            tenant_id="tenant-1",
            source_id=source.id,
            title="Refund policy",
            raw_content="Refunds are available within 30 days.",
        )
    )
    asyncio.run(
        database.ingestion_service.ingest_document(
            tenant_id="tenant-1", document_id=document.id
        )
    )

    hits = asyncio.run(
        database.search_service.search(
            tenant_id="tenant-1", agent_id="unregistered-agent", query="refund", top_k=3
        )
    )

    assert hits == []


def test_retriever_returns_chunks_within_agent_source_boundary() -> None:
    resolver = MappingAgentKnowledgeResolver()
    database = create_in_memory_database(agent_sources=resolver)
    source = asyncio.run(
        database.source_service.create_source(tenant_id="tenant-1", name="support")
    )
    resolver.register_agent(agent_id="agent-1", source_ids=[source.id])
    document = asyncio.run(
        database.document_service.create_document(
            tenant_id="tenant-1",
            source_id=source.id,
            title="Refund policy",
            raw_content="Customers may request a full refund within 30 days of purchase.",
        )
    )
    asyncio.run(
        database.ingestion_service.ingest_document(
            tenant_id="tenant-1", document_id=document.id
        )
    )

    hits = asyncio.run(
        database.search_service.search(
            tenant_id="tenant-1", agent_id="agent-1", query="refund", top_k=3
        )
    )

    assert [hit.document_id for hit in hits] == [document.id]
    assert hits[0].content == (
        "Customers may request a full refund within 30 days of purchase."
    )
    assert hits[0].score > 0


def test_retriever_does_not_cross_tenants() -> None:
    resolver = MappingAgentKnowledgeResolver()
    database = create_in_memory_database(agent_sources=resolver)
    source_one = asyncio.run(
        database.source_service.create_source(tenant_id="tenant-1", name="support")
    )
    source_two = asyncio.run(
        database.source_service.create_source(tenant_id="tenant-2", name="support")
    )
    resolver.register_agent(agent_id="agent-1", source_ids=[source_one.id])
    tenant_one_document = None
    for tenant_id, source_id in [
        ("tenant-1", source_one.id),
        ("tenant-2", source_two.id),
    ]:
        document = asyncio.run(
            database.document_service.create_document(
                tenant_id=tenant_id,
                source_id=source_id,
                title="Refund policy",
                raw_content="Customers may request a full refund within 30 days.",
            )
        )
        if tenant_id == "tenant-1":
            tenant_one_document = document
        asyncio.run(
            database.ingestion_service.ingest_document(
                tenant_id=tenant_id, document_id=document.id
            )
        )

    hits = asyncio.run(
        database.search_service.search(
            tenant_id="tenant-1", agent_id="agent-1", query="refund", top_k=3
        )
    )

    assert tenant_one_document is not None
    assert [hit.document_id for hit in hits] == [tenant_one_document.id]
    assert hits[0].content.endswith("30 days.")
    assert asyncio.run(
        database.search_service.search(
            tenant_id="tenant-2", agent_id="agent-1", query="refund", top_k=3
        )
    ) == []


def test_retriever_rejects_invalid_top_k() -> None:
    resolver = MappingAgentKnowledgeResolver({"agent-1": ["source-1"]})
    database = create_in_memory_database(agent_sources=resolver)
    with pytest.raises(ValueError):
        asyncio.run(
            database.search_service.search(
                tenant_id="tenant-1", agent_id="agent-1", query="refund", top_k=0
            )
        )


def test_document_creation_requires_existing_tenant_source() -> None:
    database = create_in_memory_database()
    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            database.document_service.create_document(
                tenant_id="tenant-1",
                source_id="missing-source",
                title="Title",
                raw_content="Content",
            )
        )
    assert excinfo.value.code == "knowledge_source_not_found"
    assert excinfo.value.status_code == 404


def test_ingestion_rejects_missing_document() -> None:
    database = create_in_memory_database()
    with pytest.raises(PlatformError) as excinfo:
        asyncio.run(
            database.ingestion_service.ingest_document(
                tenant_id="tenant-1", document_id="missing-document"
            )
        )
    assert excinfo.value.code == "knowledge_document_not_found"
    assert excinfo.value.status_code == 404


def test_ingestion_produces_deterministic_chunk_ids() -> None:
    database = create_in_memory_database()
    source = asyncio.run(
        database.source_service.create_source(tenant_id="tenant-1", name="support")
    )
    document = asyncio.run(
        database.document_service.create_document(
            tenant_id="tenant-1",
            source_id=source.id,
            title="Long policy",
            raw_content=("Policy line. " * 300),
        )
    )

    first = asyncio.run(
        database.ingestion_service.ingest_document(
            tenant_id="tenant-1", document_id=document.id
        )
    )
    second = asyncio.run(
        database.ingestion_service.ingest_document(
            tenant_id="tenant-1", document_id=document.id
        )
    )

    assert first.chunks == second.chunks
    assert first.chunks > 1


def test_build_knowledge_context_formats_retrieved_chunks() -> None:
    context = build_knowledge_context(
        [
            RetrievedChunk(
                document_id="document-1",
                chunk_id="document-1:0",
                content="Refunds are available.",
                score=0.8,
            )
        ]
    )

    assert context == "Relevant knowledge:\n[document-1:0] Refunds are available."
    assert build_knowledge_context([]) == ""
