"""Application services for the read-only platform core slice."""

from agent_service.models import Agent, Tenant
from agent_service.repositories import AgentRepository, TenantRepository


class TenantService:
    """Tenant application boundary."""

    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    async def collection_exists(self) -> bool:
        """Check tenant collection connectivity without changing data."""
        return await self._repository.collection_exists()

    async def upsert(self, tenant: Tenant) -> None:
        """Idempotently register a tenant for phone-call routing."""
        await self._repository.upsert(tenant)


class AgentService:
    """Read-only agent application boundary."""

    def __init__(self, repository: AgentRepository) -> None:
        self._repository = repository

    async def collection_exists(self) -> bool:
        """Check agent collection connectivity without changing data."""
        return await self._repository.collection_exists()

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> Agent | None:
        """Load an agent configuration without exposing database access."""
        return await self._repository.get_by_tenant_and_id(
            tenant_id=tenant_id, agent_id=agent_id
        )

    async def upsert(self, agent: Agent) -> None:
        """Idempotently register an agent so its runtime can be resolved."""
        await self._repository.upsert(agent)
