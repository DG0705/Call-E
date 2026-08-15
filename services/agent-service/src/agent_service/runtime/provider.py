"""Provider-neutral language-model interface and local test implementation."""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from agent_service.runtime.context import ConversationMessage
from agent_service.runtime.tools import ProviderToolCall, ToolDefinition


class LLMResponse(BaseModel):
    """Normalized result returned by an LLM provider."""

    text: str
    provider_name: str
    model_name: str
    usage: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[ProviderToolCall] = Field(default_factory=list)


class LLMProvider(Protocol):
    """Interface implemented by replaceable language-model providers."""

    async def generate_response(
        self,
        *,
        system_instruction: str,
        messages: list[ConversationMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse: ...


class MockLLMProvider:
    """Deterministic local provider for development and tests."""

    provider_name = "mock"
    model_name = "mock-agent-runtime-v1"

    def __init__(self, *, planned_tool_calls: list[ProviderToolCall] | None = None) -> None:
        self._planned_tool_calls = planned_tool_calls or []
        self._tool_calls_returned = False

    async def generate_response(
        self,
        *,
        system_instruction: str,
        messages: list[ConversationMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        if self._planned_tool_calls and not self._tool_calls_returned:
            self._tool_calls_returned = True
            return LLMResponse(
                text="",
                provider_name=self.provider_name,
                model_name=self.model_name,
                usage={"input_messages": len(messages)},
                tool_calls=self._planned_tool_calls,
            )
        user_message = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        return LLMResponse(
            text=f"Mock response: {user_message}",
            provider_name=self.provider_name,
            model_name=self.model_name,
            usage={"input_messages": len(messages)},
        )
