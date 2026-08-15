"""The reusable, provider-neutral agent runtime."""

from typing import Protocol

from agent_service.models import Agent
from agent_service.runtime.context import (
    ConversationContext,
    ConversationMessage,
    ConversationStore,
)
from agent_service.runtime.provider import LLMProvider, LLMResponse
from agent_service.runtime.tools import (
    ProviderToolCall,
    ToolCall,
    ToolEngine,
    ToolRegistry,
    ToolResult,
)


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
        tool_registry: ToolRegistry | None = None,
        max_tool_iterations: int = 5,
    ) -> None:
        self._configuration_loader = configuration_loader
        self._provider = provider
        self._conversation_store = conversation_store
        self._tool_engine = ToolEngine(tool_registry) if tool_registry is not None else None
        if max_tool_iterations < 1:
            raise ValueError("max_tool_iterations must be at least 1.")
        self._max_tool_iterations = max_tool_iterations

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
        provider_response = await self._generate(agent, context)
        iterations = 0
        while provider_response.tool_calls:
            if self._tool_engine is None:
                provider_response = self._tool_engine_unavailable_response(provider_response)
                break
            if iterations >= self._max_tool_iterations:
                self._append_tool_result(
                    context,
                    self._limit_result(provider_response.tool_calls[0]),
                )
                provider_response = LLMResponse(
                    text="Tool execution limit exceeded.",
                    provider_name=provider_response.provider_name,
                    model_name=provider_response.model_name,
                    usage=provider_response.usage,
                )
                break
            for provider_call in provider_response.tool_calls:
                result = await self._tool_engine.execute(
                    agent=agent,
                    call=ToolCall(
                        tool_name=provider_call.tool_name,
                        arguments=provider_call.arguments,
                        call_id=provider_call.call_id,
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        conversation_id=conversation_id,
                    ),
                )
                self._append_tool_result(context, result)
            iterations += 1
            provider_response = await self._generate(agent, context)
        context.messages.append(
            ConversationMessage(role="assistant", content=provider_response.text)
        )
        await self._conversation_store.save(context)
        return RuntimeResult(
            conversation_id=conversation_id,
            agent_id=agent_id,
            **provider_response.model_dump(),
        )

    async def _generate(
        self, agent: Agent, context: ConversationContext
    ) -> LLMResponse:
        tools = (
            self._tool_engine.registry.available_for(agent)
            if self._tool_engine is not None
            else []
        )
        return await self._provider.generate_response(
            system_instruction=self._build_system_instruction(agent),
            messages=context.messages,
            tools=tools,
        )

    @staticmethod
    def _append_tool_result(context: ConversationContext, result: ToolResult) -> None:
        context.messages.append(
            ConversationMessage(role="tool", content=result.model_dump_json())
        )

    @staticmethod
    def _limit_result(
        call: ProviderToolCall,
    ) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=False,
            error="Maximum tool iterations exceeded.",
            metadata={"code": "max_tool_iterations"},
        )

    @staticmethod
    def _tool_engine_unavailable_response(response: LLMResponse) -> LLMResponse:
        return LLMResponse(
            text="Tool execution is unavailable.",
            provider_name=response.provider_name,
            model_name=response.model_name,
            usage=response.usage,
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
