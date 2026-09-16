"""Read-only persistence boundaries for platform core data."""

from typing import Any, Protocol

from agent_service.models import AGENTS_COLLECTION, TENANTS_COLLECTION, Agent, Tenant


class CollectionNamesDatabase(Protocol):
    """The small async MongoDB surface used by the core repositories."""

    async def list_collection_names(self, **kwargs: Any) -> list[str]: ...


class AgentCollection(Protocol):
    """Read-only subset of a Mongo collection used for agents."""

    async def find_one(self, filter: dict[str, str]) -> dict[str, Any] | None: ...

    async def replace_one(
        self, filter: dict[str, str], document: dict[str, Any], **kwargs: Any
    ) -> Any: ...


class TenantCollection(Protocol):
    """Read-only subset of a Mongo collection used for tenants."""

    async def find_one(self, filter: dict[str, str]) -> dict[str, Any] | None: ...

    async def replace_one(
        self, filter: dict[str, str], document: dict[str, Any], **kwargs: Any
    ) -> Any: ...


class AgentDatabase(CollectionNamesDatabase, Protocol):
    """MongoDB surface needed by the agent repository."""

    def __getitem__(self, name: str) -> AgentCollection: ...


class TenantDatabase(CollectionNamesDatabase, Protocol):
    """MongoDB surface needed by the tenant repository."""

    def __getitem__(self, name: str) -> TenantCollection: ...



class CollectionRepository:
    """Shared read-only collection visibility check."""

    def __init__(self, database: CollectionNamesDatabase, collection_name: str) -> None:
        self._database = database
        self._collection_name = collection_name

    async def collection_exists(self) -> bool:
        """Check collection visibility without creating or changing data."""
        names = await self._database.list_collection_names(
            filter={"name": self._collection_name}
        )
        return self._collection_name in names


class TenantRepository(CollectionRepository):
    """Read-only access with idempotent seeding for the tenant collection."""

    def __init__(self, database: TenantDatabase) -> None:
        super().__init__(database, TENANTS_COLLECTION)
        self._tenants = database[TENANTS_COLLECTION]

    async def get(self, *, tenant_id: str) -> Tenant | None:
        """Load one tenant within its identifier boundary."""
        document = await self._tenants.find_one({"_id": tenant_id})
        return Tenant.model_validate(document) if document is not None else None

    async def upsert(self, tenant: Tenant) -> None:
        """Insert or replace a tenant document, preserving its identifier."""
        await self._tenants.replace_one(
            {"_id": tenant.id},
            tenant.model_dump(by_alias=True),
            upsert=True,
        )


class AgentRepository(CollectionRepository):
    """Read-only access with idempotent seeding for the agent collection."""

    def __init__(self, database: AgentDatabase) -> None:
        super().__init__(database, AGENTS_COLLECTION)
        self._agents = database[AGENTS_COLLECTION]

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> Agent | None:
        """Load one agent configuration within its tenant boundary."""
        document = await self._agents.find_one({"_id": agent_id, "tenant_id": tenant_id})
        return Agent.model_validate(document) if document is not None else None

    async def upsert(self, agent: Agent) -> None:
        """Insert or replace an agent document, preserving its identifier.

        The agent identifies itself with ``_id`` in MongoDB while the public
        API exposes ``id``; we write the storage key explicitly here.
        """
        document = agent.model_dump(by_alias=True)
        document["_id"] = document.pop("id")
        await self._agents.replace_one(
            {"_id": agent.id},
            document,
            upsert=True,
        )
