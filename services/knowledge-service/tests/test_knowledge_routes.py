"""Tests for the knowledge service API routes."""

from fastapi.testclient import TestClient

from knowledge_service.app import create_knowledge_app
from knowledge_service.database import create_in_memory_database
from knowledge_service.retrieval import MappingAgentKnowledgeResolver


def test_full_knowledge_flow_propagates_request_id() -> None:
    resolver = MappingAgentKnowledgeResolver()
    client = TestClient(create_knowledge_app(database=create_in_memory_database(agent_sources=resolver)))

    source = client.post(
        "/api/v1/knowledge/sources",
        json={"tenant_id": "tenant-1", "name": "support", "description": "Handbook"},
    )
    assert source.status_code == 200
    source_id = source.json()["id"]
    resolver.register_agent(agent_id="agent-1", source_ids=[source_id])

    document = client.post(
        "/api/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "source_id": source_id,
            "title": "Refund policy",
            "raw_content": "Customers may request a full refund within 30 days of purchase.",
        },
    )
    assert document.status_code == 200
    document_id = document.json()["id"]

    ingest = client.post(
        f"/api/v1/knowledge/documents/{document_id}/ingest",
        json={"tenant_id": "tenant-1"},
        headers={"X-Request-ID": "ingest-request"},
    )
    assert ingest.status_code == 200
    assert ingest.json()["chunks"] == 1
    assert ingest.json()["request_id"] == "ingest-request"
    assert ingest.headers["X-Request-ID"] == "ingest-request"

    search = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1", "query": "refund", "top_k": 3},
        headers={"X-Request-ID": "search-request"},
    )
    assert search.status_code == 200
    body = search.json()
    assert body["request_id"] == "search-request"
    assert search.headers["X-Request-ID"] == "search-request"
    assert [result["document_id"] for result in body["results"]] == [document_id]
    assert body["results"][0]["content"] == (
        "Customers may request a full refund within 30 days of purchase."
    )


def test_knowledge_list_endpoints_are_tenant_scoped() -> None:
    resolver = MappingAgentKnowledgeResolver()
    client = TestClient(create_knowledge_app(database=create_in_memory_database(agent_sources=resolver)))
    client.post(
        "/api/v1/knowledge/sources",
        json={"tenant_id": "tenant-1", "name": "support"},
    )
    client.post(
        "/api/v1/knowledge/sources",
        json={"tenant_id": "tenant-2", "name": "support"},
    )

    sources = client.get("/api/v1/knowledge/sources?tenant_id=tenant-1")

    assert sources.status_code == 200
    assert len(sources.json()) == 1
    assert sources.json()[0]["tenant_id"] == "tenant-1"


def test_search_is_isolated_across_tenants() -> None:
    resolver = MappingAgentKnowledgeResolver()
    client = TestClient(create_knowledge_app(database=create_in_memory_database(agent_sources=resolver)))

    def seed(tenant_id: str) -> str:
        source = client.post(
            "/api/v1/knowledge/sources", json={"tenant_id": tenant_id, "name": "support"}
        ).json()
        document = client.post(
            "/api/v1/knowledge/documents",
            json={
                "tenant_id": tenant_id,
                "source_id": source["id"],
                "title": "Refund policy",
                "raw_content": "Customers may request a full refund within 30 days.",
            },
        ).json()
        client.post(
            f"/api/v1/knowledge/documents/{document['id']}/ingest",
            json={"tenant_id": tenant_id},
        )
        return source["id"]

    tenant_one_source = seed("tenant-1")
    seed("tenant-2")
    resolver.register_agent(agent_id="agent-1", source_ids=[tenant_one_source])

    response = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1", "query": "refund", "top_k": 3},
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["document_id"] != ""


def test_search_unknown_agent_returns_empty_results() -> None:
    client = TestClient(create_knowledge_app())

    response = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "ghost", "query": "refund", "top_k": 3},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_document_creation_with_missing_source_returns_404() -> None:
    client = TestClient(create_knowledge_app())

    response = client.post(
        "/api/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "source_id": "missing-source",
            "title": "Title",
            "raw_content": "Content",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "knowledge_source_not_found"


def test_ingest_missing_document_returns_404_error_envelope() -> None:
    client = TestClient(create_knowledge_app())

    response = client.post(
        "/api/v1/knowledge/documents/missing-document/ingest",
        json={"tenant_id": "tenant-1"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "knowledge_document_not_found"


def test_search_validates_input() -> None:
    client = TestClient(create_knowledge_app())

    empty_tenant = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "", "agent_id": "agent-1", "query": "refund"},
    )
    zero_top_k = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1", "query": "refund", "top_k": 0},
    )
    huge_top_k = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1", "query": "refund", "top_k": 100},
    )

    assert empty_tenant.status_code == 422
    assert zero_top_k.status_code == 422
    assert huge_top_k.status_code == 422


def _seed_ready_document(client: TestClient, tenant_id: str) -> tuple[str, str]:
    """Create a source + ingested document; return (source_id, document_id)."""
    source = client.post(
        "/api/v1/knowledge/sources", json={"tenant_id": tenant_id, "name": "support"}
    ).json()
    document = client.post(
        "/api/v1/knowledge/documents",
        json={
            "tenant_id": tenant_id,
            "source_id": source["id"],
            "title": "Refund policy",
            "raw_content": "Customers may request a full refund within 30 days.",
        },
    ).json()
    ingest = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/ingest",
        json={"tenant_id": tenant_id},
    )
    assert ingest.status_code == 200
    return source["id"], document["id"]


def test_delete_source_cascades_documents_and_chunks() -> None:
    resolver = MappingAgentKnowledgeResolver()
    client = TestClient(
        create_knowledge_app(database=create_in_memory_database(agent_sources=resolver))
    )
    source_id, _ = _seed_ready_document(client, "tenant-1")
    resolver.register_agent(agent_id="agent-1", source_ids=[source_id])

    before = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1", "query": "refund"},
    )
    assert len(before.json()["results"]) == 1

    deleted = client.delete(
        f"/api/v1/knowledge/sources/{source_id}?tenant_id=tenant-1"
    )
    assert deleted.status_code == 204

    assert client.get("/api/v1/knowledge/sources?tenant_id=tenant-1").json() == []
    assert client.get("/api/v1/knowledge/documents?tenant_id=tenant-1").json() == []
    after = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1", "query": "refund"},
    )
    assert after.json()["results"] == []


def test_delete_document_removes_its_chunks_only() -> None:
    resolver = MappingAgentKnowledgeResolver()
    client = TestClient(
        create_knowledge_app(database=create_in_memory_database(agent_sources=resolver))
    )
    source_id, document_id = _seed_ready_document(client, "tenant-1")
    resolver.register_agent(agent_id="agent-1", source_ids=[source_id])

    deleted = client.delete(
        f"/api/v1/knowledge/documents/{document_id}?tenant_id=tenant-1"
    )
    assert deleted.status_code == 204

    # The source survives; only the document and its chunks are gone.
    assert len(client.get("/api/v1/knowledge/sources?tenant_id=tenant-1").json()) == 1
    assert client.get("/api/v1/knowledge/documents?tenant_id=tenant-1").json() == []
    after = client.post(
        "/api/v1/knowledge/search",
        json={"tenant_id": "tenant-1", "agent_id": "agent-1", "query": "refund"},
    )
    assert after.json()["results"] == []


def test_delete_is_tenant_scoped() -> None:
    client = TestClient(create_knowledge_app())
    source_id, document_id = _seed_ready_document(client, "tenant-1")

    wrong_tenant_source = client.delete(
        f"/api/v1/knowledge/sources/{source_id}?tenant_id=tenant-2"
    )
    wrong_tenant_document = client.delete(
        f"/api/v1/knowledge/documents/{document_id}?tenant_id=tenant-2"
    )

    assert wrong_tenant_source.status_code == 404
    assert wrong_tenant_document.status_code == 404
    # Data is untouched for the owning tenant.
    assert len(client.get("/api/v1/knowledge/sources?tenant_id=tenant-1").json()) == 1
    assert len(client.get("/api/v1/knowledge/documents?tenant_id=tenant-1").json()) == 1


def test_delete_missing_records_return_404() -> None:
    client = TestClient(create_knowledge_app())

    missing_source = client.delete(
        "/api/v1/knowledge/sources/ghost?tenant_id=tenant-1"
    )
    missing_document = client.delete(
        "/api/v1/knowledge/documents/ghost?tenant_id=tenant-1"
    )

    assert missing_source.status_code == 404
    assert missing_source.json()["error"]["code"] == "knowledge_source_not_found"
    assert missing_document.status_code == 404
    assert missing_document.json()["error"]["code"] == "knowledge_document_not_found"

