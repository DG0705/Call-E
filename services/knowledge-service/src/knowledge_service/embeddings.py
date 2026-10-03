"""Provider-neutral embedding interface and deterministic mock."""

import logging
import os
import re
import zlib
from math import sqrt
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field


logger = logging.getLogger("knowledge_service.embeddings")

_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")


class EmbeddingResult(BaseModel):
    """A normalized embedding vector with usage metadata."""

    vector: list[float]
    dimensions: int
    usage: dict[str, Any] = Field(default_factory=dict)


class EmbeddingProvider(Protocol):
    """Interface implemented by replaceable embedding providers."""

    provider_name: str

    async def embed_text(self, text: str) -> EmbeddingResult: ...


class MockEmbeddingProvider:
    """Deterministic local embedding provider for development and tests."""

    provider_name = "mock"
    model_name = "mock-knowledge-embeddings-v1"

    def __init__(self, *, dimensions: int = 16) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1.")
        self._dimensions = dimensions

    async def embed_text(self, text: str) -> EmbeddingResult:
        counts = [0.0] * self._dimensions
        tokens = _TOKEN_PATTERN.findall(text.lower())
        for token in tokens:
            counts[zlib.crc32(token.encode("utf-8")) % self._dimensions] += 1.0
        norm = sqrt(sum(value * value for value in counts))
        vector = [value / norm if norm else 0.0 for value in counts]
        return EmbeddingResult(
            vector=vector,
            dimensions=self._dimensions,
            usage={"tokens": len(tokens), "model": self.model_name},
        )


class EmbeddingError(Exception):
    """Raised when a real embedding provider cannot embed text."""


class OpenAICompatibleEmbeddingProvider:
    """Real embeddings via any OpenAI-compatible embeddings endpoint.

    Provider-neutral: works with OpenAI, Azure OpenAI, or self-hosted
    OpenAI-compatible servers (Ollama, text-embeddings-inference) purely
    through configuration — no vendor code paths. Requires explicit
    credentials; nothing is inferred or defaulted.
    """

    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("EMBEDDING_API_KEY is required for real embeddings.")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("EMBEDDING_BASE_URL must be an http(s) URL.")
        if not model:
            raise ValueError("EMBEDDING_MODEL is required for real embeddings.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def embed_text(self, text: str) -> EmbeddingResult:
        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json={"input": text, "model": self._model},
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            payload = response.json()
            vector = [float(value) for value in payload["data"][0]["embedding"]]
        except httpx.HTTPError as exc:
            raise EmbeddingError("Embedding request failed.") from exc
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise EmbeddingError("Embedding response was malformed.") from exc
        if not vector:
            raise EmbeddingError("Embedding response was empty.")
        return EmbeddingResult(
            vector=vector,
            dimensions=len(vector),
            usage={"model": self._model, "provider": self.provider_name},
        )

    async def close(self) -> None:
        """Release the HTTP client when this provider owns it."""
        close_client = getattr(self._client, "aclose", None)
        if close_client is not None:
            await close_client()


def create_embedding_provider() -> EmbeddingProvider:
    """Select the embedding provider from environment configuration.

    ``EMBEDDING_PROVIDER=openai_compatible`` (plus base URL, key, model)
    activates real embeddings; anything else — including unset — keeps the
    deterministic mock, so tests and credential-less development are honest
    about which provider is active.
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            api_key=os.getenv("EMBEDDING_API_KEY", ""),
            base_url=os.getenv(
                "EMBEDDING_BASE_URL", "https://api.openai.com/v1"
            ),
            model=os.getenv("EMBEDDING_MODEL", ""),
            timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30")),
        )
    logger.warning(
        "EMBEDDINGS_MOCK_ACTIVE provider=mock — retrieval is lexical-only and "
        "will miss semantically-worded questions. For production RAG set "
        "EMBEDDING_PROVIDER=openai_compatible with EMBEDDING_BASE_URL, "
        "EMBEDDING_API_KEY and EMBEDDING_MODEL."
    )
    return MockEmbeddingProvider()
