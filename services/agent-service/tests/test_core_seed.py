"""Tests for idempotent Kaari tenant/agent registration for live phone calls."""

import asyncio

from agent_service.database import CoreDatabase
from agent_service.kaari.catalog import KAARI_TENANT_ID
from agent_service.kaari.service import KAARI_AGENT_ID
from agent_service.models import AGENTS_COLLECTION, TENANTS_COLLECTION
from agent_service.repositories import AgentRepository, TenantRepository
from agent_service.services import AgentService, TenantService


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []
        self.indexes: list[dict[str, object]] = []
        self.filters: list[dict[str, str]] = []
        self.replaced: list[dict[str, object]] = []

    async def create_index(self, keys: list[object], **kwargs: object) -> str:
        self.indexes.append(kwargs)
        return str(kwargs["name"])

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

    async def replace_one(
        self, filter: dict[str, str], document: dict[str, object], **kwargs: object
    ) -> None:
        self.replaced.append(document)
        for index, existing in enumerate(self.documents):
            if all(existing.get(key) == value for key, value in filter.items()):
                self.documents[index] = document
                return
        self.documents.append(document)


class FakeCoreDatabase:
    def __init__(self) -> None:
        self.agents = FakeCollection()
        self.tenants = FakeCollection()
        self.conversations = FakeCollection()

    async def list_collection_names(self, **kwargs: object) -> list[str]:
        return []

    def __getitem__(self, name: str) -> FakeCollection:
        if name == AGENTS_COLLECTION:
            return self.agents
        if name == TENANTS_COLLECTION:
            return self.tenants
        return self.conversations


def test_seed_registers_kaari_tenant_and_agent() -> None:
    fake = FakeCoreDatabase()
    database = CoreDatabase(
        mongodb_url="mongodb://localhost:27017", database_name="call_e_core"
    )
    database.tenant_service = TenantService(TenantRepository(fake))
    database.agent_service = AgentService(AgentRepository(fake))
    database.conversation_store = type("C", (), {"ensure_indexes": _noop})()  # type: ignore[assignment]

    run(database.seed_platform_tenants())

    agent = run(
        database.agent_service.get_by_tenant_and_id(
            tenant_id=KAARI_TENANT_ID, agent_id=KAARI_AGENT_ID
        )
    )
    assert agent is not None
    assert agent.tenant_id == KAARI_TENANT_ID
    assert "search_products" in agent.allowed_tools
    assert [d for d in fake.tenants.documents if d["_id"] == KAARI_TENANT_ID]
    assert [d for d in fake.agents.documents if d["_id"] == KAARI_AGENT_ID]


def test_seed_is_idempotent() -> None:
    fake = FakeCoreDatabase()
    database = CoreDatabase(
        mongodb_url="mongodb://localhost:27017", database_name="call_e_core"
    )
    database.tenant_service = TenantService(TenantRepository(fake))
    database.agent_service = AgentService(AgentRepository(fake))
    database.conversation_store = type("C", (), {"ensure_indexes": _noop})()  # type: ignore[assignment]

    run(database.seed_platform_tenants())
    run(database.seed_platform_tenants())

    tenants = [d for d in fake.tenants.documents if d["_id"] == KAARI_TENANT_ID]
    agents = [d for d in fake.agents.documents if d["_id"] == KAARI_AGENT_ID]
    assert len(tenants) == 1
    assert len(agents) == 1


async def _noop() -> None:
    return None
