"""Tests for the HTTP knowledge retriever bridging runtime to knowledge-service."""

import asyncio

import httpx
import pytest

from agent_service.runtime.knowledge_service import KnowledgeServiceRetriever


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


class FakeAgent:
    def __init__(self, knowledge_sources: list[str]) -> None:
        self.knowledge_sources = knowledge_sources


class FakeAgentLoader:
    def __init__(self, sources: list[str] | None) -> None:
        self._sources = sources

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> FakeAgent | None:
        if self._sources is None:
            return None
        return FakeAgent(list(self._sources))


def search_handler(request: httpx.Request) -> httpx.Response:
    import json as json_module

    payload = json_module.loads(request.content.decode("utf-8"))
    assert payload["tenant_id"] == "kaari-planters"
    assert payload["agent_id"] == "kaari-sales-agent"
    assert payload["query"] == "price of DEW 28"
    assert payload["source_ids"] == ["source-1"]
    return httpx.Response(
        200,
        json={
            "results": [
                {
                    "document_id": "doc-1",
                    "chunk_id": "doc-1:0",
                    "content": "DEW | 28 | 7300 | FRP",
                    "score": 0.9,
                }
            ]
        },
        request=request,
    )


def build_retriever(
    loader: FakeAgentLoader, handler: object | None = None
) -> KnowledgeServiceRetriever:
    transport = httpx.MockTransport(handler or search_handler)  # type: ignore[arg-type]
    return KnowledgeServiceRetriever(
        base_url="http://knowledge-service:8000",
        configuration_loader=loader,  # type: ignore[arg-type]
        client=httpx.AsyncClient(transport=transport),
    )


def test_retriever_returns_grounding_chunks() -> None:
    retriever = build_retriever(FakeAgentLoader(["source-1"]))

    results = run(
        retriever.retrieve(
            tenant_id="kaari-planters",
            agent_id="kaari-sales-agent",
            query="price of DEW 28",
        )
    )

    assert len(results) == 1
    assert results[0].content == "DEW | 28 | 7300 | FRP"
    assert results[0].score == 0.9


def test_retriever_returns_empty_without_sources() -> None:
    retriever = build_retriever(FakeAgentLoader([]))

    assert (
        run(
            retriever.retrieve(
                tenant_id="kaari-planters",
                agent_id="kaari-sales-agent",
                query="anything",
            )
        )
        == []
    )


def test_retriever_returns_empty_for_unknown_agent() -> None:
    retriever = build_retriever(FakeAgentLoader(None))

    assert (
        run(
            retriever.retrieve(
                tenant_id="kaari-planters",
                agent_id="ghost",
                query="anything",
            )
        )
        == []
    )


def test_retriever_degrades_to_empty_on_http_failure() -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"}, request=request)

    retriever = build_retriever(FakeAgentLoader(["source-1"]), failing)

    assert (
        run(
            retriever.retrieve(
                tenant_id="kaari-planters",
                agent_id="kaari-sales-agent",
                query="anything",
            )
        )
        == []
    )


def test_retriever_degrades_to_empty_on_malformed_payload() -> None:
    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"bogus": 1}]}, request=request)

    retriever = build_retriever(FakeAgentLoader(["source-1"]), malformed)

    assert (
        run(
            retriever.retrieve(
                tenant_id="kaari-planters",
                agent_id="kaari-sales-agent",
                query="anything",
            )
        )
        == []
    )


def test_detach_removes_source_from_agent_record() -> None:
    from datetime import UTC, datetime

    from agent_service.models import Agent
    from agent_service.repositories import AgentRepository
    from agent_service.services import AgentService
    from tests.test_agents_routes import FakeCoreDatabase, agent_document

    database = FakeCoreDatabase(
        [agent_document("a-1", "tenant-1", "One")]
    )
    service = AgentService(AgentRepository(database))  # type: ignore[arg-type]

    async def main() -> Agent | None:
        agent = await service.get_by_tenant_and_id(
            tenant_id="tenant-1", agent_id="a-1"
        )
        assert agent is not None
        detached = agent.model_copy(
            update={"knowledge_sources": [], "updated_at": datetime.now(UTC)}
        )
        await service.update_agent(detached)
        return await service.get_by_tenant_and_id(
            tenant_id="tenant-1", agent_id="a-1"
        )

    updated = run(main())

    assert updated is not None
    assert updated.knowledge_sources == []
