"""Tests for tenant-scoped agent list/create/update routes."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agent_service.app import create_agent_app
from agent_service.models import AGENTS_COLLECTION, TENANTS_COLLECTION, Agent
from agent_service.repositories import AgentRepository
from agent_service.services import AgentService


class FakeAgentCursor:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = documents

    async def to_list(self, length: int | None) -> list[dict[str, object]]:
        if length is None:
            return list(self._documents)
        return list(self._documents[:length])


class FakeAgentCollection:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ),
            None,
        )

    def find(self, filter: dict[str, object]) -> FakeAgentCursor:
        return FakeAgentCursor(
            [
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ]
        )

    async def replace_one(
        self, filter: dict[str, str], document: dict[str, object], **kwargs: object
    ) -> None:
        for index, existing in enumerate(self.documents):
            if all(existing.get(key) == value for key, value in filter.items()):
                self.documents[index] = document
                return
        self.documents.append(document)


class FakeCoreDatabase:
    def __init__(self, agent_documents: list[dict[str, object]]) -> None:
        self.agents = FakeAgentCollection(agent_documents)

    async def list_collection_names(self, **kwargs: object) -> list[str]:
        return [AGENTS_COLLECTION, TENANTS_COLLECTION]

    def __getitem__(self, name: str) -> FakeAgentCollection:
        if name == AGENTS_COLLECTION:
            return self.agents
        raise KeyError(name)


def agent_document(agent_id: str, tenant_id: str, name: str = "Agent") -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "_id": agent_id,
        "tenant_id": tenant_id,
        "name": name,
        "description": f"{name} description",
        "role": "Sales",
        "status": "active",
        "system_prompt": "",
        "personality": "professional and helpful",
        "language": "en",
        "voice_id": None,
        "greeting": None,
        "goals": [],
        "allowed_tools": [],
        "knowledge_sources": [],
        "created_at": now,
        "updated_at": now,
    }


def build_client(documents: list[dict[str, object]] | None = None) -> TestClient:
    database = FakeCoreDatabase(documents or [])
    service = AgentService(AgentRepository(database))  # type: ignore[arg-type]
    app = create_agent_app(agent_service=service, tenant_service=None)
    return TestClient(app)


def test_list_agents_is_tenant_scoped() -> None:
    client = build_client(
        [
            agent_document("a-1", "tenant-1", "One"),
            agent_document("a-2", "tenant-1", "Two"),
            agent_document("b-1", "tenant-2", "Other"),
        ]
    )

    response = client.get("/api/v1/agents", params={"tenant_id": "tenant-1"})

    assert response.status_code == 200
    assert [agent["id"] for agent in response.json()] == ["a-1", "a-2"]


def test_list_agents_requires_tenant() -> None:
    client = build_client()

    assert client.get("/api/v1/agents").status_code == 422


def test_create_agent_generates_id_and_persists() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/agents",
        json={
            "tenant_id": "tenant-1",
            "name": "Kaari Sales Assistant",
            "description": "Handles inbound product enquiries.",
            "role": "Sales",
            "status": "active",
            "language": "en",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("kaari-sales-assistant-")
    assert body["tenant_id"] == "tenant-1"
    assert body["description"] == "Handles inbound product enquiries."
    assert body["status"] == "active"

    fetched = client.get(
        "/api/v1/agents", params={"tenant_id": "tenant-1"}
    ).json()
    assert [agent["id"] for agent in fetched] == [body["id"]]


def test_update_agent_replaces_configuration() -> None:
    client = build_client([agent_document("a-1", "tenant-1", "One")])

    response = client.patch(
        "/api/v1/agents/a-1",
        json={
            "tenant_id": "tenant-1",
            "name": "One Renamed",
            "description": "Updated.",
            "role": "Support",
            "status": "paused",
            "system_prompt": "",
            "personality": "professional and helpful",
            "language": "en",
            "voice_id": None,
            "greeting": "Hello",
            "goals": [],
            "allowed_tools": [],
            "knowledge_sources": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "a-1"
    assert body["name"] == "One Renamed"
    assert body["status"] == "paused"
    assert body["greeting"] == "Hello"


def test_update_agent_rejects_cross_tenant_access() -> None:
    client = build_client([agent_document("a-1", "tenant-1", "One")])

    response = client.patch(
        "/api/v1/agents/a-1",
        json={
            "tenant_id": "tenant-2",
            "name": "Hijacked",
            "description": "",
            "role": "assistant",
            "status": "active",
            "system_prompt": "",
            "personality": "professional and helpful",
            "language": "en",
            "voice_id": None,
            "greeting": None,
            "goals": [],
            "allowed_tools": [],
            "knowledge_sources": [],
        },
    )

    assert response.status_code == 404


def test_agent_model_accepts_description() -> None:
    agent = Agent.model_validate(agent_document("a-1", "tenant-1"))

    assert agent.description == "Agent description"


def test_generic_employee_works_without_customer_tools() -> None:
    """A generic AI employee runs STT→RAG→LLM→TTS with zero customer tools."""
    import asyncio

    from agent_service.runtime import AgentRuntime, MockLLMProvider
    from agent_service.runtime.context import InMemoryConversationStore

    def run(coro: object) -> object:
        return asyncio.run(coro)  # type: ignore[arg-type]

    service = AgentService(AgentRepository(FakeCoreDatabase([])))
    runtime = AgentRuntime(
        configuration_loader=service,
        provider=MockLLMProvider(),
        conversation_store=InMemoryConversationStore(),
    )
    created = run(
        service.create_agent(
            tenant_id="demo-co",
            name="Demo Assistant",
            description="Generic helper.",
            role="assistant",
            status="active",
            language="en",
        )
    )

    assert created.allowed_tools == []
    result = run(
        runtime.respond(
            tenant_id="demo-co",
            agent_id=created.id,
            conversation_id="conv-generic-1",
            message="hello",
        )
    )

    assert result.text == "Mock response: hello"
    assert result.tool_execution_history == []
