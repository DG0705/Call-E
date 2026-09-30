"""Persistent cache for pre-generated agent greeting audio.

The greeting is a static call-level opening statement, so synthesizing it
synchronously on every call wastes seconds of paid TTS latency. This module
caches greeting PCM keyed by tenant, agent, greeting text, voice, model, and
output format: a configuration change naturally misses and regenerates, while
stale entries for the same agent/voice are pruned on every store.

Only raw PCM bytes are persisted (MongoDB BSON bytes or process memory);
cache keys and status are logged, never audio content.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from voice_service.audio import AudioChunk


def greeting_cache_key(
    *,
    tenant_id: str,
    agent_id: str,
    text: str,
    voice_id: str | None,
    model: str | None,
    output_format: str,
) -> str:
    """Build the deterministic cache key for one greeting configuration."""
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    voice = voice_id or "default-voice"
    return "|".join(
        [tenant_id, agent_id, text_hash, voice, model or "default-model", output_format]
    )


class GreetingAudioStore(Protocol):
    """Persistence boundary for cached greeting audio."""

    async def get(self, key: str) -> AudioChunk | None: ...

    async def put(self, key: str, audio: AudioChunk) -> None: ...

    async def prune(
        self, *, tenant_id: str, agent_id: str, voice_id: str | None, keep_key: str
    ) -> None:
        """Drop stale greeting entries for an agent/voice except the current key."""
        ...


class InMemoryGreetingAudioStore:
    """Development-only greeting cache with no external dependencies."""

    def __init__(self) -> None:
        self._audio: dict[str, AudioChunk] = {}

    async def get(self, key: str) -> AudioChunk | None:
        return self._audio.get(key)

    async def put(self, key: str, audio: AudioChunk) -> None:
        self._audio[key] = audio

    async def prune(
        self, *, tenant_id: str, agent_id: str, voice_id: str | None, keep_key: str
    ) -> None:
        prefix = "|".join([tenant_id, agent_id])
        for stored_key in [
            candidate
            for candidate in self._audio
            if candidate.startswith(prefix) and candidate != keep_key
        ]:
            del self._audio[stored_key]


class MongoGreetingAudioStore:
    """Tenant-isolated greeting audio persistence in MongoDB."""

    COLLECTION = "greeting_audio"

    def __init__(self, database: Any) -> None:
        self._collection = database[self.COLLECTION]

    async def get(self, key: str) -> AudioChunk | None:
        document = await self._collection.find_one({"_id": key})
        if document is None:
            return None
        return AudioChunk(
            data=bytes(document["audio"]),
            format="pcm",
            sample_rate=int(document.get("sample_rate", 8000)),
            channels=int(document.get("channels", 1)),
            sample_width=int(document.get("sample_width", 2)),
        )

    async def put(self, key: str, audio: AudioChunk) -> None:
        tenant_id, agent_id = key.split("|", 2)[:2]
        await self._collection.update_one(
            {"_id": key},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "audio": bytes(audio.data),
                    "sample_rate": audio.sample_rate,
                    "channels": audio.channels,
                    "sample_width": audio.sample_width,
                }
            },
            upsert=True,
        )

    async def prune(
        self, *, tenant_id: str, agent_id: str, voice_id: str | None, keep_key: str
    ) -> None:
        await self._collection.delete_many(
            {"tenant_id": tenant_id, "agent_id": agent_id, "_id": {"$ne": keep_key}}
        )
