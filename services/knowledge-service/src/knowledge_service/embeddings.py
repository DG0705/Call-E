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

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]: ...


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

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch locally, preserving input order."""
        return [await self.embed_text(text) for text in texts]


class EmbeddingError(Exception):
    """Raised when a real embedding provider cannot embed text."""


def _batch_order_key(pair: tuple[int, Any]) -> int:
    """Sort key preserving request order for a batch embeddings response.

    Uses each item's ``index`` when the provider supplies one and falls back
    to the item's original position otherwise, so a missing or malformed
    ``index`` never reorders or drops vectors.
    """
    position, item = pair
    if isinstance(item, dict):
        index = item.get("index")
        if isinstance(index, int):
            return index
    return position


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
        payload = await self._post({"input": text, "model": self._model})
        return self._result(self._parse_embeddings(payload, expected=1)[0])

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch in one request, preserving input ordering.

        OpenAI-compatible servers return one object per input carrying its
        ``index``; results are sorted on it so vectors align with ``texts``
        even if a provider reorders the array. An empty batch makes no call.
        """
        if not texts:
            return []
        payload = await self._post({"input": list(texts), "model": self._model})
        vectors = self._parse_embeddings(payload, expected=len(texts))
        return [self._result(vector) for vector in vectors]

    async def _post(self, body: dict[str, Any]) -> Any:
        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            # Generic message only: the request carries the API key, so it is
            # never echoed into the exception or logs.
            raise EmbeddingError("Embedding request failed.") from exc

    def _parse_embeddings(self, payload: Any, *, expected: int) -> list[list[float]]:
        try:
            data = payload["data"]
            ordered = [
                item
                for _, item in sorted(enumerate(data), key=_batch_order_key)
            ]
            vectors = [
                [float(value) for value in item["embedding"]] for item in ordered
            ]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise EmbeddingError("Embedding response was malformed.") from exc
        if len(vectors) != expected:
            raise EmbeddingError(
                "Embedding response count did not match the requested inputs."
            )
        if any(not vector for vector in vectors):
            raise EmbeddingError("Embedding response was empty.")
        if len({len(vector) for vector in vectors}) != 1:
            raise EmbeddingError("Embedding response had inconsistent dimensions.")
        return vectors

    def _result(self, vector: list[float]) -> EmbeddingResult:
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
    activates real embeddings. Unset, empty, or ``mock`` keeps the
    deterministic mock so tests and credential-less development stay honest
    about which provider is active. An explicitly-set unknown value is a
    misconfiguration and fails loudly instead of silently downgrading to
    lexical-only retrieval.
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
    if provider not in ("", "mock"):
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER '{provider}'. "
            "Expected 'mock' or 'openai_compatible'."
        )
    logger.warning(
        "EMBEDDINGS_MOCK_ACTIVE provider=mock — retrieval is lexical-only and "
        "will miss semantically-worded questions. For production RAG set "
        "EMBEDDING_PROVIDER=openai_compatible with EMBEDDING_BASE_URL, "
        "EMBEDDING_API_KEY and EMBEDDING_MODEL."
    )
    return MockEmbeddingProvider()
