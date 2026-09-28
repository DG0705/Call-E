"""Tests for the Mongo index-shape migration of call and session stores.

Stored documents carry their identifier as ``_id`` (the pydantic alias of
``call_id``/``session_id``), so the tenant-scoped unique indexes must target
``_id``. The fakes below enforce uniqueness the way MongoDB does — a missing
indexed field counts as null — which reproduces the production E11000 shape
for the legacy index and proves the corrected shape accepts it.
"""

import asyncio
from datetime import UTC, datetime

from voice_service.models import VOICE_SESSIONS_COLLECTION, VoiceSession
from voice_service.session_store import MongoVoiceSessionStore
from voice_service.telephony.models import CALLS_COLLECTION, TelephonyCall
from voice_service.telephony.store import CALL_LOOKUP_INDEX, MongoCallStore


class FakeIndexConflict(Exception):
    """Stand-in for a same-name/different-keys index conflict."""


class FakeDuplicateKey(Exception):
    """Stand-in for a unique-index duplicate-key violation."""


class FakeMongoCollection:
    """In-memory collection enforcing unique indexes like MongoDB does."""

    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []
        self.indexes: dict[str, dict[str, object]] = {}
        self.dropped: list[str] = []
        self.fail_next_create: bool = False

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: object) -> str:
        name = str(kwargs["name"])
        if self.fail_next_create:
            self.fail_next_create = False
            raise FakeIndexConflict(f"index {name} already exists with other keys")
        self.indexes[name] = {"keys": keys, "unique": kwargs.get("unique", False)}
        return name

    async def drop_index(self, name: str) -> None:
        if name not in self.indexes:
            raise FakeIndexConflict(f"index {name} not found")
        del self.indexes[name]
        self.dropped.append(name)

    async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ),
            None,
        )

    async def insert_one(self, document: dict[str, object]) -> None:
        for spec in self.indexes.values():
            if not spec["unique"]:
                continue
            key = tuple(document.get(field) for field, _ in spec["keys"])  # type: ignore[union-attr]
            for existing in self.documents:
                existing_key = tuple(existing.get(field) for field, _ in spec["keys"])  # type: ignore[union-attr]
                if existing_key == key:
                    raise FakeDuplicateKey(f"duplicate key {key}")
        self.documents.append(dict(document))

    async def update_one(
        self, filter: dict[str, str], update: dict[str, object], **kwargs: object
    ) -> None:
        document = await self.find_one(filter)
        if document is not None:
            document.update(update["$set"])  # type: ignore[arg-type]


class FakeCallDatabase:
    def __init__(self, collection: FakeMongoCollection) -> None:
        self.calls = collection

    def __getitem__(self, name: str) -> FakeMongoCollection:
        assert name == CALLS_COLLECTION
        return self.calls


class FakeSessionDatabase:
    def __init__(self, collection: FakeMongoCollection) -> None:
        self.sessions = collection

    def __getitem__(self, name: str) -> FakeMongoCollection:
        assert name == VOICE_SESSIONS_COLLECTION
        return self.sessions


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def call_record(call_id: str, tenant_id: str = "kaari-planters") -> TelephonyCall:
    now = datetime.now(UTC)
    return TelephonyCall(
        call_id=call_id,
        tenant_id=tenant_id,
        agent_id="kaari-sales-agent",
        conversation_id="conversation-1",
        destination_number="1000",
        direction="inbound",
        created_at=now,
        updated_at=now,
    )


def session_record(session_id: str, tenant_id: str = "kaari-planters") -> VoiceSession:
    now = datetime.now(UTC)
    return VoiceSession(
        session_id=session_id,
        tenant_id=tenant_id,
        agent_id="kaari-sales-agent",
        conversation_id="conversation-1",
        created_at=now,
        updated_at=now,
    )


def test_call_index_targets_stored_id_field() -> None:
    collection = FakeMongoCollection()
    store = MongoCallStore(FakeCallDatabase(collection))

    run(store.ensure_indexes())

    assert collection.indexes[CALL_LOOKUP_INDEX]["keys"] == [
        ("tenant_id", 1),
        ("_id", 1),
    ]
    assert collection.indexes[CALL_LOOKUP_INDEX]["unique"] is True
    assert collection.dropped == []


def test_call_legacy_index_is_migrated() -> None:
    collection = FakeMongoCollection()
    collection.indexes[CALL_LOOKUP_INDEX] = {
        "keys": [("tenant_id", 1), ("call_id", 1)],
        "unique": True,
    }
    collection.fail_next_create = True
    store = MongoCallStore(FakeCallDatabase(collection))

    run(store.ensure_indexes())

    assert collection.dropped == [CALL_LOOKUP_INDEX]
    assert collection.indexes[CALL_LOOKUP_INDEX]["keys"] == [
        ("tenant_id", 1),
        ("_id", 1),
    ]


def test_call_ensure_indexes_is_idempotent() -> None:
    collection = FakeMongoCollection()
    store = MongoCallStore(FakeCallDatabase(collection))

    run(store.ensure_indexes())
    run(store.ensure_indexes())

    assert collection.dropped == []
    assert list(collection.indexes) == [CALL_LOOKUP_INDEX]


def test_same_tenant_persists_multiple_calls() -> None:
    collection = FakeMongoCollection()
    store = MongoCallStore(FakeCallDatabase(collection))
    run(store.ensure_indexes())

    run(store.create(call_record("call-1")))
    run(store.create(call_record("call-2")))

    assert run(store.get(tenant_id="kaari-planters", call_id="call-1")) is not None
    assert run(store.get(tenant_id="kaari-planters", call_id="call-2")) is not None


def test_stored_call_document_uses_id_key() -> None:
    collection = FakeMongoCollection()
    store = MongoCallStore(FakeCallDatabase(collection))
    run(store.ensure_indexes())

    run(store.create(call_record("call-1")))

    assert collection.documents[0]["_id"] == "call-1"
    assert "call_id" not in collection.documents[0]


def test_call_tenant_isolation_preserved() -> None:
    collection = FakeMongoCollection()
    store = MongoCallStore(FakeCallDatabase(collection))
    run(store.ensure_indexes())

    run(store.create(call_record("call-1", tenant_id="tenant-a")))

    assert run(store.get(tenant_id="tenant-b", call_id="call-1")) is None
    assert run(store.get(tenant_id="tenant-a", call_id="call-1")) is not None


def test_session_index_targets_stored_id_field() -> None:
    collection = FakeMongoCollection()
    store = MongoVoiceSessionStore(FakeSessionDatabase(collection))

    run(store.ensure_indexes())

    from voice_service.session_store import VOICE_SESSION_LOOKUP_INDEX

    assert collection.indexes[VOICE_SESSION_LOOKUP_INDEX]["keys"] == [
        ("tenant_id", 1),
        ("_id", 1),
    ]
    assert collection.indexes[VOICE_SESSION_LOOKUP_INDEX]["unique"] is True


def test_session_legacy_index_is_migrated() -> None:
    from voice_service.session_store import VOICE_SESSION_LOOKUP_INDEX

    collection = FakeMongoCollection()
    collection.indexes[VOICE_SESSION_LOOKUP_INDEX] = {
        "keys": [("tenant_id", 1), ("session_id", 1)],
        "unique": True,
    }
    collection.fail_next_create = True
    store = MongoVoiceSessionStore(FakeSessionDatabase(collection))

    run(store.ensure_indexes())

    assert collection.dropped == [VOICE_SESSION_LOOKUP_INDEX]
    assert collection.indexes[VOICE_SESSION_LOOKUP_INDEX]["keys"] == [
        ("tenant_id", 1),
        ("_id", 1),
    ]


def test_same_tenant_persists_multiple_sessions() -> None:
    collection = FakeMongoCollection()
    store = MongoVoiceSessionStore(FakeSessionDatabase(collection))
    run(store.ensure_indexes())

    run(store.create(session_record("session-1")))
    run(store.create(session_record("session-2")))

    assert run(store.get(tenant_id="kaari-planters", session_id="session-1")) is not None
    assert run(store.get(tenant_id="kaari-planters", session_id="session-2")) is not None
    assert "session_id" not in collection.documents[0]
