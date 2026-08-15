"""Provider-neutral embedding interface and deterministic mock."""

import re
import zlib
from math import sqrt
from typing import Any, Protocol

from pydantic import BaseModel, Field


_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")


class EmbeddingResult(BaseModel):
    """A normalized embedding vector with usage metadata."""

    vector: list[float]
    dimensions: int
    usage: dict[str, Any] = Field(default_factory=dict)


class EmbeddingProvider(Protocol):
    """Interface implemented by replaceable embedding providers."""

    async def embed_text(self, text: str) -> EmbeddingResult: ...


class MockEmbeddingProvider:
    """Deterministic local embedding provider for development and tests."""

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
