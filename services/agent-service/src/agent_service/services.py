"""Application services for the read-only platform core slice."""

from agent_service.models import Agent
from agent_service.repositories import AgentRepository, TenantRepository


class TenantService:
    """Read-only tenant application boundary."""

    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    async def collection_exists(self) -> bool:
        """Check tenant collection connectivity without changing data."""
        return await self._repository.collection_exists()


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
