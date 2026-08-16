"""Persistence boundaries for tenant-scoped voice sessions."""

from datetime import UTC, datetime
from typing import Any, Protocol

from voice_service.models import VOICE_SESSIONS_COLLECTION, VoiceSession


VOICE_SESSION_LOOKUP_INDEX = "tenant_session"


class VoiceSessionCollection(Protocol):
    """Mongo collection operations used by voice session persistence."""

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str: ...

    async def find_one(self, filter: dict[str, str]) -> dict[str, Any] | None: ...

    async def insert_one(self, document: dict[str, Any]) -> Any: ...

    async def update_one(
        self, filter: dict[str, str], update: dict[str, Any], **kwargs: Any
    ) -> Any: ...


class VoiceSessionDatabase(Protocol):
    """Small database surface needed by the voice session store."""

    def __getitem__(self, name: str) -> VoiceSessionCollection: ...


class VoiceSessionStore(Protocol):
    """Persistence boundary for voice session lifecycle state."""

    async def ensure_indexes(self) -> None: ...

    async def create(self, session: VoiceSession) -> None: ...

    async def get(self, *, tenant_id: str, session_id: str) -> VoiceSession | None: ...

    async def save(self, session: VoiceSession) -> None: ...


class MongoVoiceSessionStore:
    """Tenant-isolated voice session persistence in MongoDB."""

    def __init__(self, database: VoiceSessionDatabase) -> None:
        self._collection = database[VOICE_SESSIONS_COLLECTION]

    async def ensure_indexes(self) -> None:
        """Create the tenant-scoped lookup index used by the current flow."""
        await self._collection.create_index(
            [("tenant_id", 1), ("session_id", 1)],
            name=VOICE_SESSION_LOOKUP_INDEX,
            unique=True,
        )

    async def create(self, session: VoiceSession) -> None:
        """Insert a new session with its store-owned identifier."""
        now = datetime.now(UTC)
        session.created_at = now
        session.updated_at = now
        await self._collection.insert_one(session.model_dump(by_alias=True))

    async def get(self, *, tenant_id: str, session_id: str) -> VoiceSession | None:
        """Load a session only when the tenant identifier matches."""
        document = await self._collection.find_one(
            {"_id": session_id, "tenant_id": tenant_id}
        )
        return VoiceSession.model_validate(document) if document is not None else None

    async def save(self, session: VoiceSession) -> None:
        """Persist the full session state without moving its identifier."""
        session.updated_at = datetime.now(UTC)
        await self._collection.update_one(
            {"_id": session.session_id, "tenant_id": session.tenant_id},
            {"$set": session.model_dump(by_alias=True)},
        )


class InMemoryVoiceSessionStore:
    """Development-only session store with no external dependencies."""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], VoiceSession] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def create(self, session: VoiceSession) -> None:
        key = (session.tenant_id, session.session_id)
        if key in self._sessions:
            raise ValueError("Voice session already exists.")
        self._sessions[key] = session

    async def get(self, *, tenant_id: str, session_id: str) -> VoiceSession | None:
        return self._sessions.get((tenant_id, session_id))

    async def save(self, session: VoiceSession) -> None:
        self._sessions[(session.tenant_id, session.session_id)] = session
