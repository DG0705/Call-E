"""Tests for upload/website ingestion, status, embeddings, and retrieval."""

import asyncio
import io
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from knowledge_service.app import create_knowledge_app
from knowledge_service.database import create_in_memory_database
from knowledge_service.embeddings import (
    EmbeddingError,
    MockEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    create_embedding_provider,
)
from knowledge_service.models import DOCUMENT_STATUS_READY
from knowledge_service.retrieval import MappingAgentKnowledgeResolver
from knowledge_service.services import UploadedFile
from knowledge_service.website import FetchError, HttpxWebsiteFetcher, validate_website_url


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def build_client(**kwargs: object) -> TestClient:
    return TestClient(create_knowledge_app(database=create_in_memory_database(**kwargs)))  # type: ignore[arg-type]


def test_upload_ingests_pdf_and_reports_status() -> None:
    from tests.test_extraction import make_pdf_bytes

    client = build_client()
    pdf = make_pdf_bytes(["DEW 28 price 7300"])

    response = client.post(
        "/api/v1/knowledge/uploads",
        data={"tenant_id": "tenant-1"},
        files={"files": ("catalog.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 200
    files = response.json()["files"]
    assert len(files) == 1
    assert files[0]["file_name"] == "catalog.pdf"
    assert files[0]["status"] == DOCUMENT_STATUS_READY
    assert files[0]["chunks"] == 1
    assert files[0]["error"] is None
    assert files[0]["source_id"]
    assert files[0]["document_id"]

    document = client.get(
        f"/api/v1/knowledge/documents/{files[0]['document_id']}",
        params={"tenant_id": "tenant-1"},
    )
    assert document.status_code == 200
    assert document.json()["status"] == DOCUMENT_STATUS_READY
    assert document.json()["file_name"] == "catalog.pdf"
    assert "DEW 28 price 7300" in document.json()["raw_content"]


def test_upload_rejects_unsupported_type_without_records() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/knowledge/uploads",
        data={"tenant_id": "tenant-1"},
        files={"files": ("archive.zip", b"\x00\x01", "application/zip")},
    )

    assert response.status_code == 200
    file_result = response.json()["files"][0]
    assert file_result["status"] == "failed"
    assert "Unsupported file type" in file_result["error"]
    assert file_result["document_id"] is None


def test_upload_enforces_size_limit() -> None:
    from knowledge_service.database import KnowledgeDatabase
    from knowledge_service.files import LocalFileStorage

    database = create_in_memory_database()
    database.upload_service._max_file_bytes = 10
    client = TestClient(create_knowledge_app(database=database))

    response = client.post(
        "/api/v1/knowledge/uploads",
        data={"tenant_id": "tenant-1"},
        files={"files": ("big.txt", b"x" * 11, "text/plain")},
    )

    assert response.status_code == 200
    assert "exceeds" in response.json()["files"][0]["error"]


def test_upload_rejects_empty_request() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/knowledge/uploads", data={"tenant_id": "tenant-1"}
    )

    assert response.status_code == 422


def test_spreadsheet_rows_retrieve_individually() -> None:
    from tests.test_extraction import make_xlsx_bytes

    client = build_client()
    uploaded = client.post(
        "/api/v1/knowledge/uploads",
        data={"tenant_id": "tenant-1"},
        files={"files": ("prices.xlsx", make_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()["files"][0]

    assert uploaded["status"] == DOCUMENT_STATUS_READY
    assert uploaded["chunks"] > 1

    results = client.post(
        "/api/v1/knowledge/search",
        json={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "query": "What is the price of DEW 28?",
            "top_k": 3,
            "source_ids": [uploaded["source_id"]],
        },
    ).json()["results"]

    assert results
    assert "7300" in results[0]["content"]
    assert "DEW" in results[0]["content"] and "28" in results[0]["content"]


def test_upload_supports_multiple_files_with_per_file_results() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/knowledge/uploads",
        data={"tenant_id": "tenant-1"},
        files=[
            ("files", ("a.txt", b"First policy note.", "text/plain")),
            ("files", ("b.txt", b"Second policy note.", "text/plain")),
        ],
    )

    assert response.status_code == 200
    files = response.json()["files"]
    assert [item["file_name"] for item in files] == ["a.txt", "b.txt"]
    assert all(item["status"] == DOCUMENT_STATUS_READY for item in files)


def test_failed_ingestion_preserves_failed_state() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/knowledge/uploads",
        data={"tenant_id": "tenant-1"},
        files={"files": ("empty.pdf", b"%PDF-1.4 not a real pdf", "application/pdf")},
    )

    assert response.status_code == 200
    file_result = response.json()["files"][0]
    assert file_result["status"] == "failed"
    assert file_result["error"]
    assert file_result["document_id"] is not None

    document = client.get(
        f"/api/v1/knowledge/documents/{file_result['document_id']}",
        params={"tenant_id": "tenant-1"},
    )
    assert document.json()["status"] == "failed"
    assert document.json()["chunks"] == 0


def test_reingestion_replaces_stale_chunks() -> None:
    client = build_client()
    source = client.post(
        "/api/v1/knowledge/sources",
        json={"tenant_id": "tenant-1", "name": "policy"},
    ).json()["id"]
    document = client.post(
        "/api/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "source_id": source,
            "title": "Policy",
            "raw_content": "Old refund wording that must disappear entirely.",
        },
    ).json()["id"]

    assert (
        client.post(
            f"/api/v1/knowledge/documents/{document}/ingest",
            json={"tenant_id": "tenant-1"},
        ).json()["chunks"]
        == 1
    )
    before = client.post(
        "/api/v1/knowledge/search",
        json={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "query": "refund wording",
            "top_k": 5,
            "source_ids": [source],
        },
    ).json()["results"]
    assert any("Old refund wording" in result["content"] for result in before)

    database = client.app.state.database  # type: ignore[attr-defined]
    stored = run(
        database.document_service.get_document(
            tenant_id="tenant-1", document_id=document
        )
    )
    stored.raw_content = "Completely new shipping wording with no overlap."
    run(database.document_service.save_document(stored))
    assert (
        client.post(
            f"/api/v1/knowledge/documents/{document}/ingest",
            json={"tenant_id": "tenant-1"},
        ).json()["chunks"]
        == 1
    )

    after = client.post(
        "/api/v1/knowledge/search",
        json={
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "query": "refund wording",
            "top_k": 5,
            "source_ids": [source],
        },
    ).json()["results"]
    assert all("Old refund wording" not in result["content"] for result in after)


def test_search_honors_caller_source_ids_without_mapping() -> None:
    client = build_client()
    first = client.post(
        "/api/v1/knowledge/sources",
        json={"tenant_id": "tenant-1", "name": "one"},
    ).json()["id"]
    second = client.post(
        "/api/v1/knowledge/sources",
        json={"tenant_id": "tenant-1", "name": "two"},
    ).json()["id"]
    for source_id, text in (
        (first, "Alpha unique marker phrase for scoping."),
        (second, "Beta unique marker phrase for scoping."),
    ):
        document = client.post(
            "/api/v1/knowledge/documents",
            json={
                "tenant_id": "tenant-1",
                "source_id": source_id,
                "title": "Doc",
                "raw_content": text,
            },
        ).json()["id"]
        client.post(
            f"/api/v1/knowledge/documents/{document}/ingest",
            json={"tenant_id": "tenant-1"},
        )

    results = client.post(
        "/api/v1/knowledge/search",
        json={
            "tenant_id": "tenant-1",
            "agent_id": "unmapped-agent",
            "query": "unique marker phrase",
            "top_k": 5,
            "source_ids": [second],
        },
    ).json()["results"]

    assert results
    assert all("Beta" in result["content"] for result in results)


def test_search_without_sources_returns_nothing() -> None:
    client = build_client()

    results = client.post(
        "/api/v1/knowledge/search",
        json={
            "tenant_id": "tenant-1",
            "agent_id": "unmapped-agent",
            "query": "anything",
            "top_k": 3,
        },
    ).json()["results"]

    assert results == []


def test_uploads_are_tenant_isolated() -> None:
    client = build_client()
    client.post(
        "/api/v1/knowledge/uploads",
        data={"tenant_id": "tenant-1"},
        files={"files": ("a.txt", b"Tenant one secret note.", "text/plain")},
    )

    other = client.get(
        "/api/v1/knowledge/documents", params={"tenant_id": "tenant-2"}
    ).json()
    assert other == []

    missing = client.get(
        "/api/v1/knowledge/documents/some-id", params={"tenant_id": "tenant-2"}
    )
    assert missing.status_code == 404


# --- Website ingestion ---


class FakeDNS:
    """Control socket.getaddrinfo results for SSRF tests."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping
        self._original = socket.getaddrinfo

    def __enter__(self) -> "FakeDNS":
        original = self._original
        mapping = self._mapping

        def fake(host: str, *args: object, **kwargs: object) -> list[object]:
            if host not in mapping:
                raise socket.gaierror("no such host")
            return [(2, 1, 6, "", (address, 0)) for address in mapping[host]]  # type: ignore[misc]

        socket.getaddrinfo = fake  # type: ignore[assignment]
        return self

    def __exit__(self, *args: object) -> None:
        socket.getaddrinfo = self._original  # type: ignore[assignment]


def test_website_url_validation_rejects_dangerous_targets() -> None:
    with FakeDNS({}):
        with pytest.raises(Exception):
            validate_website_url("ftp://example.com/file")
        with pytest.raises(Exception):
            validate_website_url("http://localhost:8000/x")
        with pytest.raises(Exception):
            validate_website_url("http://127.0.0.1/x")
        with pytest.raises(Exception):
            validate_website_url("http://169.254.169.254/latest/meta-data/")
        with pytest.raises(Exception):
            validate_website_url("http://10.0.0.5/internal")
        with pytest.raises(Exception):
            validate_website_url("http://192.168.1.20/internal")
        with pytest.raises(Exception):
            validate_website_url("http://[::1]/x")


def test_website_url_validation_accepts_public_hosts() -> None:
    with FakeDNS({"example.com": ["93.184.216.34"]}):
        assert (
            validate_website_url("https://example.com/page")
            == "https://example.com/page"
        )


def test_website_ingest_fetches_extracts_and_indexes() -> None:
    from knowledge_service.website import HttpxWebsiteFetcher

    html = (
        "<html><head><title>Kaari Planters</title></head><body>"
        "<nav>Menu</nav><h1>DEW 28</h1><p>Price 7300 INR, made to order.</p>"
        "</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=html.encode("utf-8"),
            request=request,
        )

    client = build_client()
    fetcher = HttpxWebsiteFetcher(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    database = client.app.state.database  # type: ignore[attr-defined]

    async def main() -> object:
        return await database.upload_service.ingest_website(
            tenant_id="tenant-1", url="https://example.com/", name=None, fetcher=fetcher
        )

    with FakeDNS({"example.com": ["93.184.216.34"]}):
        document = run(main())

    assert document.status == DOCUMENT_STATUS_READY
    assert document.source_url == "https://example.com/"
    assert document.title == "Kaari Planters"
    assert "Menu" not in document.raw_content
    assert "DEW 28" in document.raw_content


def test_website_ingest_refuses_redirect_to_private_host() -> None:
    from knowledge_service.website import HttpxWebsiteFetcher

    def handler(request: httpx.Request) -> httpx.Response:
        if "example.com" in str(request.url):
            return httpx.Response(
                307,
                headers={"location": "http://127.0.0.1:8000/admin"},
                request=request,
            )
        return httpx.Response(200, content=b"hello", request=request)

    fetcher = HttpxWebsiteFetcher(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    async def main() -> None:
        await fetcher.fetch_page("https://example.com/")

    with FakeDNS({"example.com": ["93.184.216.34"], "127.0.0.1": ["127.0.0.1"]}):
        with pytest.raises(Exception):
            run(main())


def test_website_ingest_enforces_size_limit() -> None:
    from knowledge_service.website import HttpxWebsiteFetcher

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<p>" + b"x" * 100 + b"</p>",
            request=request,
        )

    fetcher = HttpxWebsiteFetcher(
        max_bytes=10,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def main() -> None:
        await fetcher.fetch_page("https://example.com/")

    with FakeDNS({"example.com": ["93.184.216.34"]}):
        with pytest.raises(Exception):
            run(main())


def test_website_route_rejects_unsafe_url_without_records() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/knowledge/websites",
        json={"tenant_id": "tenant-1", "url": "http://169.254.169.254/"},
    )

    assert response.status_code == 422
    assert (
        client.get(
            "/api/v1/knowledge/documents", params={"tenant_id": "tenant-1"}
        ).json()
        == []
    )


# --- Embeddings ---


def test_embedding_factory_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)

    provider = create_embedding_provider()

    assert provider.provider_name == "mock"


def test_embedding_factory_selects_real_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "secret")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    provider = create_embedding_provider()

    assert provider.provider_name == "openai_compatible"


def test_embedding_factory_refuses_real_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    with pytest.raises(ValueError):
        create_embedding_provider()


def test_real_embedding_provider_posts_and_returns_vector() -> None:
    from knowledge_service.embeddings import OpenAICompatibleEmbeddingProvider

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as json_module

        seen["body"] = json_module.loads(request.content.decode("utf-8"))
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2, 0.3]}]},
            request=request,
        )

    provider = OpenAICompatibleEmbeddingProvider(
        api_key="secret",
        base_url="https://example.invalid/v1",
        model="text-embedding-3-small",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = run(provider.embed_text("DEW 28 price"))

    assert result.vector == [0.1, 0.2, 0.3]
    assert result.dimensions == 3
    assert seen["body"] == {"input": "DEW 28 price", "model": "text-embedding-3-small"}
    assert seen["auth"] == "Bearer secret"


def test_real_embedding_provider_maps_http_failure() -> None:
    from knowledge_service.embeddings import OpenAICompatibleEmbeddingProvider

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"}, request=request)

    provider = OpenAICompatibleEmbeddingProvider(
        api_key="secret",
        base_url="https://example.invalid/v1",
        model="text-embedding-3-small",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(EmbeddingError):
        run(provider.embed_text("hello"))


def test_database_reports_active_embedder() -> None:
    from knowledge_service.database import create_in_memory_database as build

    assert build().embedder_name == "mock"
    assert build(embedder=MockEmbeddingProvider()).embedder_name == "mock"


def test_embedding_factory_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "totally-made-up")

    with pytest.raises(ValueError):
        create_embedding_provider()


def test_embedding_factory_treats_empty_provider_as_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The shipped .env sets EMBEDDING_PROVIDER= (empty); that must stay mock so
    # the service still starts without credentials rather than failing loudly.
    monkeypatch.setenv("EMBEDDING_PROVIDER", "")

    assert create_embedding_provider().provider_name == "mock"


def _real_provider(handler: object) -> OpenAICompatibleEmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider(
        api_key="secret",
        base_url="https://example.invalid/v1",
        model="text-embedding-3-small",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
    )


def test_real_embedding_provider_batches_and_preserves_order() -> None:
    import json as json_module

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json_module.loads(request.content.decode("utf-8"))
        # Deliberately out of order; each item carries its request index.
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [1.0, 1.0]},
                    {"index": 0, "embedding": [0.0, 0.0]},
                    {"index": 2, "embedding": [2.0, 2.0]},
                ]
            },
            request=request,
        )

    results = run(_real_provider(handler).embed_texts(["a", "b", "c"]))

    assert seen["body"] == {
        "input": ["a", "b", "c"],
        "model": "text-embedding-3-small",
    }
    assert [result.vector for result in results] == [  # type: ignore[attr-defined]
        [0.0, 0.0],
        [1.0, 1.0],
        [2.0, 2.0],
    ]
    assert all(result.dimensions == 2 for result in results)  # type: ignore[attr-defined]


def test_real_embedding_provider_batch_count_mismatch_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1]}]},
            request=request,
        )

    with pytest.raises(EmbeddingError):
        run(_real_provider(handler).embed_texts(["a", "b"]))


def test_real_embedding_provider_malformed_response_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True}, request=request)

    with pytest.raises(EmbeddingError):
        run(_real_provider(handler).embed_text("hello"))


def test_real_embedding_provider_inconsistent_dimensions_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4, 0.5]},
                ]
            },
            request=request,
        )

    with pytest.raises(EmbeddingError):
        run(_real_provider(handler).embed_texts(["a", "b"]))


def test_real_embedding_provider_empty_batch_skips_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("embed_texts([]) must not perform a network call")

    assert run(_real_provider(handler).embed_texts([])) == []


def test_ingestion_embeds_in_bounded_batches() -> None:
    from knowledge_service.embeddings import EmbeddingResult
    from knowledge_service.models import KnowledgeDocument
    from knowledge_service.services import KnowledgeIngestionService
    from knowledge_service.storage import StoredChunk

    batch_sizes: list[int] = []

    class _CountingEmbedder:
        provider_name = "counting"

        async def embed_text(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(
                vector=[1.0, 0.0], dimensions=2, usage={"model": "counting-model"}
            )

        async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
            batch_sizes.append(len(texts))
            return [await self.embed_text(text) for text in texts]

    class _RecordingRepository:
        def __init__(self) -> None:
            self.saved: list[StoredChunk] = []

        async def delete_document(self, *, tenant_id: str, document_id: str) -> int:
            return 0

        async def save_chunk(self, chunk: StoredChunk) -> None:
            self.saved.append(chunk)

    class _StubDocuments:
        async def get_document(
            self, *, tenant_id: str, document_id: str
        ) -> KnowledgeDocument:
            return KnowledgeDocument(
                id=document_id,
                tenant_id=tenant_id,
                source_id="source-1",
                title="Long",
                source_type="text",
                raw_content="word " * 900,
                created_at="2026-08-03T12:00:00Z",
                updated_at="2026-08-03T12:00:00Z",
            )

        async def save_document(self, document: KnowledgeDocument) -> None:
            return None

    repository = _RecordingRepository()
    service = KnowledgeIngestionService(
        documents=_StubDocuments(),
        embedder=_CountingEmbedder(),
        repository=repository,
        batch_size=2,
    )

    result = run(service.ingest_document(tenant_id="tenant-1", document_id="document-1"))

    assert result.chunks >= 3  # type: ignore[attr-defined]
    assert batch_sizes and all(size <= 2 for size in batch_sizes)
    assert len(batch_sizes) >= 2
    assert sum(batch_sizes) == result.chunks  # type: ignore[attr-defined]
    assert len(repository.saved) == result.chunks  # type: ignore[attr-defined]
    assert all(chunk.embedding_model == "counting-model" for chunk in repository.saved)
    assert [chunk.index for chunk in repository.saved] == list(range(result.chunks))  # type: ignore[attr-defined]
