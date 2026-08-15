"""Deterministic knowledge text normalization and chunking."""

import html
import re

from pydantic import BaseModel, Field

from knowledge_service.models import SourceType


_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")


class ChunkingConfig(BaseModel):
    """Tunable deterministic chunking parameters."""

    chunk_size: int = Field(default=1000, ge=1)
    chunk_overlap: int = Field(default=200, ge=0)

    def model_post_init(self, __context: object) -> None:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")


def normalize_text(text: str, *, source_type: SourceType) -> str:
    """Normalize raw document content into a clean chunking input."""
    if source_type == "html":
        text = _HTML_TAG_PATTERN.sub(" ", text)
        text = html.unescape(text)
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def chunk_text(text: str, *, config: ChunkingConfig) -> list[str]:
    """Split normalized text into deterministic overlapping chunks."""
    if not text:
        return []
    if len(text) <= config.chunk_size:
        content = text.strip()
        return [content] if content else []
    chunks: list[str] = []
    start = 0
    size = config.chunk_size
    overlap = config.chunk_overlap
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + 1, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        if next_start <= start:
            break
        start = next_start
    return chunks
