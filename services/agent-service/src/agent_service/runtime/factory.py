"""Factory for selecting configured agent-runtime LLM providers."""

from typing import Callable

from agent_service.runtime.config import LLMSettings
from agent_service.runtime.groq_provider import GroqClient, GroqProvider
from agent_service.runtime.provider import LLMProvider, MockLLMProvider


class LLMProviderConfigurationError(ValueError):
    """Raised when runtime provider settings are incomplete or unsupported."""


class LLMProviderFactory:
    """Construct the configured provider while retaining the neutral boundary."""

    @staticmethod
    def create(
        settings: LLMSettings,
        *,
        groq_client_factory: Callable[[str], GroqClient] | None = None,
    ) -> LLMProvider:
        """Return mock or Groq, falling back safely when no key is configured."""
        if settings.provider == "mock":
            return MockLLMProvider()
        if settings.provider != "groq":
            raise LLMProviderConfigurationError(
                f"Unsupported LLM_PROVIDER '{settings.provider}'. Use 'mock' or 'groq'."
            )
        if settings.groq_api_key is None:
            return MockLLMProvider()
        if settings.groq_model is None:
            raise LLMProviderConfigurationError(
                "GROQ_MODEL must be set when LLM_PROVIDER is 'groq'."
            )
        client = (
            groq_client_factory(settings.groq_api_key)
            if groq_client_factory is not None
            else None
        )
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            client=client,
        )
