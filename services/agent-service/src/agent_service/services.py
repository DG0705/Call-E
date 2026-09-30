"""Application services for the read-only platform core slice."""

import re
import uuid
from datetime import UTC, datetime

from agent_service.models import Agent, Tenant
from agent_service.repositories import AgentRepository, TenantRepository


def generate_agent_id(name: str) -> str:
    """Build a URL-safe unique agent id from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agent"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


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

    async def list_by_tenant(
        self, *, tenant_id: str, limit: int = 100
    ) -> list[Agent]:
        """List agent configurations visible to one tenant."""
        return await self._repository.list_by_tenant(
            tenant_id=tenant_id, limit=limit
        )

    async def create_agent(
        self,
        *,
        tenant_id: str,
        name: str,
        description: str = "",
        role: str = "assistant",
        status: str = "draft",
        system_prompt: str = "",
        personality: str = "professional and helpful",
        language: str = "en",
        voice_id: str | None = None,
        greeting: str | None = None,
        goals: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        knowledge_sources: list[str] | None = None,
    ) -> Agent:
        """Persist a new tenant-scoped agent configuration with a generated id."""
        now = datetime.now(UTC)
        agent = Agent(
            id=generate_agent_id(name),
            tenant_id=tenant_id,
            name=name,
            description=description,
            role=role,
            status=status,
            system_prompt=system_prompt,
            personality=personality,
            language=language,
            voice_id=voice_id,
            greeting=greeting,
            goals=goals or [],
            allowed_tools=allowed_tools or [],
            knowledge_sources=knowledge_sources or [],
            created_at=now,
            updated_at=now,
        )
        await self._repository.upsert(agent)
        return agent

    async def update_agent(self, agent: Agent) -> Agent:
        """Replace a tenant-scoped agent configuration, refreshing its timestamp."""
        stored = agent.model_copy(update={"updated_at": datetime.now(UTC)})
        await self._repository.upsert(stored)
        return stored

    async def upsert(self, agent: Agent) -> None:
        """Idempotently register an agent so its runtime can be resolved."""
        await self._repository.upsert(agent)
