"""MongoDB wiring for tenant and agent core data."""

import os
from datetime import UTC, datetime

from pymongo import AsyncMongoClient

from agent_service.models import Tenant
from agent_service.repositories import AgentRepository, TenantRepository
from agent_service.runtime.mongo_store import MongoConversationStore
from agent_service.services import AgentService, TenantService


DEFAULT_CORE_DATABASE = "call_e_core"
MONGODB_URL_ENV_VAR = "MONGODB_URL"
CORE_DATABASE_ENV_VAR = "CORE_DATABASE_NAME"

SEED_ON_STARTUP_ENV_VAR = "AGENT_SERVICE_SEED"
DEFAULT_SEED_ON_STARTUP = True


class CoreDatabase:
    """Own the MongoDB client lifecycle for the platform core slice."""

    def __init__(self, *, mongodb_url: str, database_name: str) -> None:
        self._client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=1_000)
        database = self._client[database_name]
        self.tenant_service = TenantService(TenantRepository(database))
        self.agent_service = AgentService(AgentRepository(database))
        self.conversation_store = MongoConversationStore(database)

    async def initialize(self) -> None:
        """Create indexes and register the Kaari tenant/agent for phone calls."""
        await self.conversation_store.ensure_indexes()
        if _should_seed():
            await self.seed_platform_tenants()

    async def seed_platform_tenants(self) -> None:
        """Idempotently register the Kaari tenant and sales agent.

        The real phone-call MVP requires the Kaari agent configuration to be
        resolvable by the agent runtime through MongoDB. This is safe to run on
        every startup because both upserts are idempotent.
        """
        from agent_service.kaari.service import KAARI_TENANT_ID, create_kaari_agent

        now = datetime.now(UTC)
        tenant = Tenant(
            id=KAARI_TENANT_ID,
            name="Kaari Planters",
            status="active",
            created_at=now,
            updated_at=now,
        )
        await self.tenant_service.upsert(tenant)
        await self.agent_service.upsert(create_kaari_agent(now=now))

    async def close(self) -> None:
        """Release the MongoDB client during application shutdown."""
        await self._client.close()


def create_core_database() -> CoreDatabase:
    """Build core persistence boundaries from the service runtime configuration."""
    return CoreDatabase(
        mongodb_url=os.getenv(MONGODB_URL_ENV_VAR, "mongodb://localhost:27017"),
        database_name=os.getenv(CORE_DATABASE_ENV_VAR, DEFAULT_CORE_DATABASE),
    )


def _should_seed() -> bool:
    value = os.getenv(SEED_ON_STARTUP_ENV_VAR, "").strip().lower()
    if value == "":
        return DEFAULT_SEED_ON_STARTUP
    return value in ("1", "true", "yes", "on")
