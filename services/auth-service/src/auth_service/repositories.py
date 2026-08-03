"""Persistence boundaries for auth-owned data."""

from typing import Any, Protocol

from auth_service.models import AUTH_ACCOUNTS_COLLECTION


class CollectionNamesDatabase(Protocol):
    """The small async MongoDB surface required by this service."""

    async def list_collection_names(self, **kwargs: Any) -> list[str]: ...


class AuthAccountRepository:
    """Read-only access to the future auth account collection."""

    def __init__(self, database: CollectionNamesDatabase) -> None:
        self._database = database

    async def collection_exists(self) -> bool:
        """Check whether the auth account collection is visible to MongoDB."""
        names = await self._database.list_collection_names(
            filter={"name": AUTH_ACCOUNTS_COLLECTION}
        )
        return AUTH_ACCOUNTS_COLLECTION in names
