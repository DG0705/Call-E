"""The reusable, provider-neutral agent runtime."""

from typing import Protocol

from agent_service.models import Agent
from agent_service.runtime.context import (
    ConversationContext,
    ConversationMessage,
    ConversationStore,
)
from agent_service.runtime.provider import LLMProvider, LLMResponse


class AgentConfigurationLoader(Protocol):
    """Application-facing configuration boundary used by the runtime."""

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> Agent | None: ...


class AgentNotFoundError(Exception):
    """Raised when an agent does not exist for the supplied tenant."""


class RuntimeResult(LLMResponse):
    """Provider result paired with the persisted conversation context."""

    conversation_id: str
    agent_id: str


class AgentRuntime:
    """Run agent conversations using supplied services, not database clients."""

    def __init__(
        self,
        *,
        configuration_loader: AgentConfigurationLoader,
        provider: LLMProvider,
        conversation_store: ConversationStore,
    ) -> None:
        self._configuration_loader = configuration_loader
        self._provider = provider
        self._conversation_store = conversation_store

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> Agent:
        """Load the tenant-scoped configuration required by the runtime."""
        agent = await self._configuration_loader.get_by_tenant_and_id(
            tenant_id=tenant_id, agent_id=agent_id
        )
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        """Append user input, call the provider, and retain local context."""
        agent = await self.get_agent(tenant_id=tenant_id, agent_id=agent_id)
        context = await self._conversation_store.get(
            tenant_id=tenant_id, agent_id=agent_id, conversation_id=conversation_id
        )
        if context is None:
            context = ConversationContext(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                messages=[
                    ConversationMessage(
                        role="system", content=self._build_system_instruction(agent)
                    )
                ],
            )
        context.messages.append(ConversationMessage(role="user", content=message))
        provider_response = await self._provider.generate_response(
            system_instruction=self._build_system_instruction(agent), messages=context.messages
        )
        context.messages.append(
            ConversationMessage(role="assistant", content=provider_response.text)
        )
        await self._conversation_store.save(context)
        return RuntimeResult(
            conversation_id=conversation_id,
            agent_id=agent_id,
            **provider_response.model_dump(),
        )

    @staticmethod
    def _build_system_instruction(agent: Agent) -> str:
        """Build the provider-neutral instruction from agent configuration."""
        parts = [
            f"You are {agent.name}, acting as a {agent.role}.",
            f"Personality: {agent.personality}.",
            f"Respond in {agent.language}.",
        ]
        if agent.system_prompt:
            parts.append(agent.system_prompt)
        if agent.goals:
            parts.append(f"Goals: {', '.join(agent.goals)}.")
        return "\n".join(parts)
