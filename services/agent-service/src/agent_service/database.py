"""MongoDB wiring for tenant and agent core data."""

import os

from pymongo import AsyncMongoClient

from agent_service.repositories import AgentRepository, TenantRepository


DEFAULT_CORE_DATABASE = "call_e_core"
MONGODB_URL_ENV_VAR = "MONGODB_URL"
CORE_DATABASE_ENV_VAR = "CORE_DATABASE_NAME"


class CoreDatabase:
    """Own the MongoDB client lifecycle for the platform core slice."""

    def __init__(self, *, mongodb_url: str, database_name: str) -> None:
        self._client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=1_000)
        database = self._client[database_name]
        self.tenants = TenantRepository(database)
        self.agents = AgentRepository(database)

    async def close(self) -> None:
        """Release the MongoDB client during application shutdown."""
        await self._client.close()


def create_core_database() -> CoreDatabase:
    """Build core persistence boundaries from the service runtime configuration."""
    return CoreDatabase(
        mongodb_url=os.getenv(MONGODB_URL_ENV_VAR, "mongodb://localhost:27017"),
        database_name=os.getenv(CORE_DATABASE_ENV_VAR, DEFAULT_CORE_DATABASE),
    )
