"""Groq implementation of the provider-neutral LLM interface."""

from collections.abc import Mapping
from typing import Any, Protocol

from agent_service.runtime.context import ConversationMessage
from agent_service.runtime.provider import LLMResponse


class GroqCompletions(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class GroqChat(Protocol):
    completions: GroqCompletions


class GroqClient(Protocol):
    chat: GroqChat


class GroqProvider:
    """Generate responses using Groq's official asynchronous Python SDK."""

    provider_name = "groq"

    def __init__(
        self, *, api_key: str, model: str, client: GroqClient | None = None
    ) -> None:
        if not api_key:
            raise ValueError("GROQ_API_KEY is required to configure GroqProvider.")
        if not model:
            raise ValueError("GROQ_MODEL is required to configure GroqProvider.")
        self._model = model
        self._client = client or self._create_client(api_key)

    async def generate_response(
        self, *, system_instruction: str, messages: list[ConversationMessage]
    ) -> LLMResponse:
        """Send the runtime-built instruction and context to Groq unchanged."""
        completion = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_instruction},
                *[
                    {"role": message.role, "content": message.content}
                    for message in messages
                    if message.role != "system"
                ],
            ],
        )
        text = completion.choices[0].message.content or ""
        return LLMResponse(
            text=text,
            provider_name=self.provider_name,
            model_name=self._model,
            usage=_normalize_usage(getattr(completion, "usage", None)),
        )

    @staticmethod
    def _create_client(api_key: str) -> GroqClient:
        """Import the optional SDK only when the Groq provider is selected."""
        from groq import AsyncGroq

        return AsyncGroq(api_key=api_key)


def _normalize_usage(usage: Any) -> dict[str, int]:
    """Expose common completion usage fields when Groq supplies them."""
    names = ("prompt_tokens", "completion_tokens", "total_tokens")
    values: dict[str, int] = {}
    for name in names:
        value = usage.get(name) if isinstance(usage, Mapping) else getattr(usage, name, None)
        if value is not None:
            values[name] = int(value)
    return values
