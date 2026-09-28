"""Shared Mongo index migration for voice persistence.

Stored voice documents carry their identifier as ``_id`` (the pydantic alias
of ``call_id``/``session_id``), so tenant-scoped unique indexes must target
``_id``. Legacy deployments may still hold a same-named index on the
non-existent ``*_id``-suffixed field (indexed as null), which rejects every
second document per tenant with a duplicate-key error. This helper migrates
exactly that known index, nothing else.
"""

from typing import Any, Protocol


class IndexManagedCollection(Protocol):
    """Minimal Mongo collection surface for index migration."""

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str: ...

    async def drop_index(self, name: str) -> Any: ...


async def ensure_lookup_index(
    collection: IndexManagedCollection, *, name: str, keys: list[tuple[str, int]]
) -> None:
    """Create a unique lookup index, migrating a same-named legacy shape.

    Fresh databases and already-migrated databases take the fast path: a
    single idempotent ``create_index``. Only when creation fails (the known
    same-name/different-keys conflict) is the legacy index dropped — by its
    exact known name — before recreating. Genuine failures still surface from
    the final ``create_index`` call.
    """
    try:
        await collection.create_index(keys, name=name, unique=True)
    except Exception:
        try:
            await collection.drop_index(name)
        except Exception:
            pass
        await collection.create_index(keys, name=name, unique=True)
