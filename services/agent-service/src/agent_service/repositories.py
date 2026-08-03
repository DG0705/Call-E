"""Read-only persistence boundaries for platform core data."""

from typing import Any, Protocol

from agent_service.models import AGENTS_COLLECTION, TENANTS_COLLECTION


class CollectionNamesDatabase(Protocol):
    """The small async MongoDB surface used by the core repositories."""

    async def list_collection_names(self, **kwargs: Any) -> list[str]: ...


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
    """Read-only access to the tenant collection."""

    def __init__(self, database: CollectionNamesDatabase) -> None:
        super().__init__(database, TENANTS_COLLECTION)


class AgentRepository(CollectionRepository):
    """Read-only access to the agent collection."""

    def __init__(self, database: CollectionNamesDatabase) -> None:
        super().__init__(database, AGENTS_COLLECTION)
