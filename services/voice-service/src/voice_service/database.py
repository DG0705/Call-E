"""MongoDB wiring for voice session persistence."""

import os

from pymongo import AsyncMongoClient

from voice_service.session_store import MongoVoiceSessionStore

DEFAULT_VOICE_DATABASE = "call_e_voice"
MONGODB_URL_ENV_VAR = "MONGODB_URL"
VOICE_DATABASE_ENV_VAR = "VOICE_DATABASE_NAME"


class VoiceDatabase:
    """Own the MongoDB client lifecycle for the voice service slice."""

    def __init__(self, *, mongodb_url: str, database_name: str) -> None:
        self._client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=1_000)
        self.session_store = MongoVoiceSessionStore(self._client[database_name])

    async def initialize(self) -> None:
        """Create indexes for persistence owned by the voice service."""
        await self.session_store.ensure_indexes()

    async def close(self) -> None:
        """Release the MongoDB client during application shutdown."""
        await self._client.close()


def create_voice_database() -> VoiceDatabase:
    """Build voice persistence boundaries from the service runtime configuration."""
    return VoiceDatabase(
        mongodb_url=os.getenv(MONGODB_URL_ENV_VAR, "mongodb://localhost:27017"),
        database_name=os.getenv(VOICE_DATABASE_ENV_VAR, DEFAULT_VOICE_DATABASE),
    )
