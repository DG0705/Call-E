"""Persistence boundaries for normalized telephony call records."""

from datetime import UTC, datetime
from typing import Any, Protocol

from voice_service.telephony.models import CALLS_COLLECTION, TelephonyCall

CALL_LOOKUP_INDEX = "tenant_call"


class CallCollection(Protocol):
    """Mongo collection operations used by call persistence."""

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str: ...

    async def find_one(self, filter: dict[str, str]) -> dict[str, Any] | None: ...

    async def insert_one(self, document: dict[str, Any]) -> Any: ...

    async def update_one(
        self, filter: dict[str, str], update: dict[str, Any], **kwargs: Any
    ) -> Any: ...


class CallDatabase(Protocol):
    """Small database surface needed by the call store."""

    def __getitem__(self, name: str) -> CallCollection: ...


class CallStore(Protocol):
    """Persistence boundary for normalized telephony call records."""

    async def ensure_indexes(self) -> None: ...

    async def create(self, call: TelephonyCall) -> None: ...

    async def get(self, *, tenant_id: str, call_id: str) -> TelephonyCall | None: ...

    async def save(self, call: TelephonyCall) -> None: ...


class MongoCallStore:
    """Tenant-isolated call record persistence in MongoDB."""

    def __init__(self, database: CallDatabase) -> None:
        self._collection = database[CALLS_COLLECTION]

    async def ensure_indexes(self) -> None:
        """Create the tenant-scoped lookup index used by the current flow."""
        await self._collection.create_index(
            [("tenant_id", 1), ("call_id", 1)],
            name=CALL_LOOKUP_INDEX,
            unique=True,
        )

    async def create(self, call: TelephonyCall) -> None:
        """Insert a new call record with its store-owned identifier."""
        now = datetime.now(UTC)
        call.created_at = now
        call.updated_at = now
        await self._collection.insert_one(call.model_dump(by_alias=True))

    async def get(self, *, tenant_id: str, call_id: str) -> TelephonyCall | None:
        """Load a call record only when the tenant identifier matches."""
        document = await self._collection.find_one(
            {"_id": call_id, "tenant_id": tenant_id}
        )
        return TelephonyCall.model_validate(document) if document is not None else None

    async def save(self, call: TelephonyCall) -> None:
        """Persist the full call state without moving its identifier."""
        call.updated_at = datetime.now(UTC)
        await self._collection.update_one(
            {"_id": call.call_id, "tenant_id": call.tenant_id},
            {"$set": call.model_dump(by_alias=True)},
        )


class InMemoryCallStore:
    """Development-only call store with no external dependencies."""

    def __init__(self) -> None:
        self._calls: dict[tuple[str, str], TelephonyCall] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def create(self, call: TelephonyCall) -> None:
        key = (call.tenant_id, call.call_id)
        if key in self._calls:
            raise ValueError("Call record already exists.")
        self._calls[key] = call

    async def get(self, *, tenant_id: str, call_id: str) -> TelephonyCall | None:
        return self._calls.get((tenant_id, call_id))

    async def save(self, call: TelephonyCall) -> None:
        self._calls[(call.tenant_id, call.call_id)] = call
