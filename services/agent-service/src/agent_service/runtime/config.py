"""Runtime provider configuration loaded from the service environment."""

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Configuration for selecting an LLM provider at application startup."""

    provider: str = "mock"
    groq_api_key: str | None = None
    groq_model: str | None = None
    max_tool_iterations: int = 5


def load_llm_settings() -> LLMSettings:
    """Load provider settings without supplying secrets or model defaults."""
    return LLMSettings(
        provider=os.getenv("LLM_PROVIDER", "mock").strip().lower(),
        groq_api_key=_optional_environment_value("GROQ_API_KEY"),
        groq_model=_optional_environment_value("GROQ_MODEL"),
        max_tool_iterations=_load_max_tool_iterations(),
    )


def _optional_environment_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _load_max_tool_iterations() -> int:
    try:
        value = int(os.getenv("MAX_TOOL_ITERATIONS", "5"))
    except ValueError:
        return 5
    return value if value >= 1 else 5
