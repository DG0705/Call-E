"""Provider-neutral language-model interface and local test implementation."""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from agent_service.runtime.context import ConversationMessage


class LLMResponse(BaseModel):
    """Normalized result returned by an LLM provider."""

    text: str
    provider_name: str
    model_name: str
    usage: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(Protocol):
    """Interface implemented by replaceable language-model providers."""

    async def generate_response(
        self, *, system_instruction: str, messages: list[ConversationMessage]
    ) -> LLMResponse: ...


class MockLLMProvider:
    """Deterministic local provider for development and tests."""

    provider_name = "mock"
    model_name = "mock-agent-runtime-v1"

    async def generate_response(
        self, *, system_instruction: str, messages: list[ConversationMessage]
    ) -> LLMResponse:
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
