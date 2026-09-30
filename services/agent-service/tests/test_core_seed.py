"""Tests proving a fresh installation seeds no customer data.

The platform starts empty: no tenants, no AI employees, no knowledge.
Customers create everything through the API/frontend. Kaari domain modules
remain available as test fixtures, but production startup must not depend
on them.
"""

import asyncio

from agent_service.database import CoreDatabase
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

    async def find(self, filter: dict[str, object]) -> object:
        class _Cursor:
            def __init__(self, documents: list[dict[str, object]]) -> None:
                self._documents = documents

            async def to_list(self, length: int | None) -> list[dict[str, object]]:
                return list(self._documents[:length] if length else self._documents)

        return _Cursor(
            [
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ]
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


def _database(fake: FakeCoreDatabase) -> CoreDatabase:
    database = CoreDatabase(
        mongodb_url="mongodb://localhost:27017", database_name="call_e_core"
    )
    database.tenant_service = TenantService(TenantRepository(fake))
    database.agent_service = AgentService(AgentRepository(fake))
    database.conversation_store = type("C", (), {"ensure_indexes": _noop})()  # type: ignore[assignment]
    return database


def test_fresh_system_starts_with_no_tenants_or_agents() -> None:
    fake = FakeCoreDatabase()
    database = _database(fake)

    run(database.initialize())

    assert fake.tenants.documents == []
    assert fake.agents.documents == []


def test_startup_does_not_seed_kaari() -> None:
    fake = FakeCoreDatabase()
    database = _database(fake)

    run(database.initialize())

    assert not hasattr(database, "seed_platform_tenants")
    assert all("kaari" not in str(document) for document in fake.agents.documents)


def test_production_startup_needs_no_kaari_imports() -> None:
    import agent_service.app as app_module
    import agent_service.database as database_module

    assert "KaariService" not in dir(app_module)
    assert "KaariService" not in dir(database_module)


async def _noop(self: object) -> None:
    return None
