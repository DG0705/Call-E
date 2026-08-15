"""Tests for the read-only tenant and agent core routes."""

import asyncio

from fastapi.testclient import TestClient

from agent_service.app import create_agent_app
from agent_service.models import AGENTS_COLLECTION, TENANTS_COLLECTION, Agent, Tenant
from agent_service.repositories import AgentRepository, TenantRepository
from agent_service.runtime import AgentRuntime, MockLLMProvider
from agent_service.runtime.context import (
    ConversationContext,
    ConversationMessage,
    InMemoryConversationStore,
)
from agent_service.services import AgentService, TenantService


class FakeAgentCollection:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents
        self.filters: list[dict[str, str]] = []

    async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
        self.filters.append(filter)
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ),
            None,
        )


class FakeCoreDatabase:
    def __init__(
        self, collections: list[str], agent_documents: list[dict[str, object]] | None = None
    ) -> None:
        self.collections = collections
        self.filters: list[dict[str, str]] = []
        self.agents = FakeAgentCollection(agent_documents or [])

    async def list_collection_names(self, **kwargs: object) -> list[str]:
        self.filters.append(kwargs["filter"])
        return self.collections

    def __getitem__(self, name: str) -> FakeAgentCollection:
        assert name == AGENTS_COLLECTION
        return self.agents


def agent_document() -> dict[str, object]:
    return {
        "_id": "agent-1",
        "tenant_id": "tenant-1",
        "name": "Receptionist",
        "role": "customer support assistant",
        "system_prompt": "Help customers clearly.",
        "personality": "warm and concise",
        "language": "en",
        "voice_id": "neutral-voice",
        "goals": ["Resolve simple questions"],
        "allowed_tools": ["lookup_order"],
        "knowledge_sources": ["support-handbook"],
        "created_at": "2026-08-03T12:00:00Z",
        "updated_at": "2026-08-03T12:00:00Z",
    }


def test_tenant_model_serializes_mongo_id() -> None:
    tenant = Tenant.model_validate(
        {
            "_id": "tenant-1",
            "name": "Example tenant",
            "created_at": "2026-08-03T12:00:00Z",
            "updated_at": "2026-08-03T12:00:00Z",
        }
    )

    assert tenant.status == "active"
    assert tenant.model_dump(by_alias=True)["_id"] == "tenant-1"


def test_agent_model_is_tenant_scoped_and_provider_neutral() -> None:
    agent = Agent.model_validate(agent_document())

    assert agent.tenant_id == "tenant-1"
    assert agent.role == "customer support assistant"
    assert agent.allowed_tools == ["lookup_order"]
    assert agent.model_dump()["id"] == "agent-1"


def test_repositories_and_services_check_only_their_collection() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])

    assert asyncio.run(TenantService(TenantRepository(database)).collection_exists()) is True
    assert asyncio.run(AgentService(AgentRepository(database)).collection_exists()) is True
    assert database.filters == [
        {"name": TENANTS_COLLECTION},
        {"name": AGENTS_COLLECTION},
    ]


def test_agent_repository_loads_only_within_tenant() -> None:
    database = FakeCoreDatabase([AGENTS_COLLECTION], [agent_document()])
    service = AgentService(AgentRepository(database))

    agent = asyncio.run(
        service.get_by_tenant_and_id(tenant_id="tenant-1", agent_id="agent-1")
    )
    missing = asyncio.run(
        service.get_by_tenant_and_id(tenant_id="other-tenant", agent_id="agent-1")
    )

    assert agent is not None
    assert agent.name == "Receptionist"
    assert missing is None
    assert database.agents.filters == [
        {"_id": "agent-1", "tenant_id": "tenant-1"},
        {"_id": "agent-1", "tenant_id": "other-tenant"},
    ]


def test_conversation_context_and_mock_provider() -> None:
    context = ConversationContext(
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conversation-1",
        messages=[ConversationMessage(role="user", content="Hello")],
        metadata={"channel": "runtime-test"},
    )
    provider_response = asyncio.run(
        MockLLMProvider().generate_response(
            system_instruction="Be helpful.", messages=context.messages
        )
    )

    assert context.metadata["channel"] == "runtime-test"
    assert provider_response.text == "Mock response: Hello"
    assert provider_response.provider_name == "mock"


def test_agent_runtime_builds_context_and_persists_messages() -> None:
    database = FakeCoreDatabase([AGENTS_COLLECTION], [agent_document()])
    store = InMemoryConversationStore()
    runtime = AgentRuntime(
        configuration_loader=AgentService(AgentRepository(database)),
        provider=MockLLMProvider(),
        conversation_store=store,
    )

    result = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Can you help me?",
        )
    )
    context = asyncio.run(
        store.get(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    assert result.text == "Mock response: Can you help me?"
    assert context is not None
    assert [message.role for message in context.messages] == ["system", "user", "assistant"]


def test_tenant_status_propagates_request_id() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])
    client = TestClient(
        create_agent_app(
            tenant_service=TenantService(TenantRepository(database)),
            agent_service=AgentService(AgentRepository(database)),
        )
    )

    response = client.get(
        "/api/v1/tenants/status", headers={"X-Request-ID": "tenant-status-request"}
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Call-E tenant core"
    assert response.json()["request_id"] == "tenant-status-request"
    assert response.headers["X-Request-ID"] == "tenant-status-request"


def test_agent_status_and_database_check_are_read_only() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])
    client = TestClient(
        create_agent_app(
            tenant_service=TenantService(TenantRepository(database)),
            agent_service=AgentService(AgentRepository(database)),
        )
    )

    status = client.get("/api/v1/agents/status")
    ping = client.get("/api/v1/agents/ping-db", headers={"X-Request-ID": "agent-db-request"})

    assert status.status_code == 200
    assert status.json()["description"] == "Call-E agent core"
    assert ping.status_code == 200
    assert ping.json()["request_id"] == "agent-db-request"
    assert database.filters == [{"name": AGENTS_COLLECTION}]


def test_tenant_database_check_is_read_only() -> None:
    database = FakeCoreDatabase([TENANTS_COLLECTION, AGENTS_COLLECTION])
    client = TestClient(
        create_agent_app(
            tenant_service=TenantService(TenantRepository(database)),
            agent_service=AgentService(AgentRepository(database)),
        )
    )

    response = client.get("/api/v1/tenants/ping-db")

    assert response.status_code == 200
    assert database.filters == [{"name": TENANTS_COLLECTION}]


def test_agent_configuration_and_runtime_test_endpoint() -> None:
    database = FakeCoreDatabase([AGENTS_COLLECTION], [agent_document()])
    client = TestClient(
        create_agent_app(
            tenant_service=TenantService(TenantRepository(database)),
            agent_service=AgentService(AgentRepository(database)),
        )
    )

    configuration = client.get("/api/v1/agents/agent-1?tenant_id=tenant-1")
    runtime = client.post(
        "/api/v1/agents/agent-1/runtime/test?tenant_id=tenant-1",
        headers={"X-Request-ID": "runtime-request"},
        json={"conversation_id": "conversation-1", "message": "Hello runtime"},
    )

    assert configuration.status_code == 200
    assert configuration.json()["id"] == "agent-1"
    assert configuration.json()["allowed_tools"] == ["lookup_order"]
    assert runtime.status_code == 200
    assert runtime.json() == {
        "conversation_id": "conversation-1",
        "agent_id": "agent-1",
        "response": "Mock response: Hello runtime",
        "provider": "mock",
        "model": "mock-agent-runtime-v1",
        "request_id": "runtime-request",
    }
    assert runtime.headers["X-Request-ID"] == "runtime-request"
