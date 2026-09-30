"""Local file storage for knowledge uploads.

Uploaded bytes never go into MongoDB: they live under a tenant-scoped
directory on a mounted volume (development default) behind this small
protocol, so object storage can replace the implementation later without
touching ingestion logic. Stored paths are server-local and are never
exposed to the frontend.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Protocol


class FileStorage(Protocol):
    """Persistence boundary for raw upload bytes."""

    async def save(
        self, *, tenant_id: str, filename: str, content: bytes
    ) -> str:
        """Persist upload bytes and return the server-local storage key."""
        ...

    async def read(self, key: str) -> bytes:
        """Read previously stored bytes by storage key."""
        ...

    async def delete(self, key: str) -> None:
        """Remove stored bytes best-effort."""
        ...


def _safe_tenant_segment(tenant_id: str) -> str:
    segment = re.sub(r"[^a-zA-Z0-9_-]", "_", tenant_id).strip("_") or "tenant"
    return segment[:64]


class LocalFileStorage:
    """Development file storage rooted at a mounted volume directory."""

    def __init__(self, root_directory: str) -> None:
        self._root = root_directory

    def _path_for(self, key: str) -> str:
        tenant_segment, _, name = key.partition("/")
        if not tenant_segment or not name or "/" in name or ".." in key:
            raise ValueError("Invalid storage key.")
        return os.path.join(self._root, tenant_segment, name)

    async def save(
        self, *, tenant_id: str, filename: str, content: bytes
    ) -> str:
        suffix = os.path.splitext(filename)[1].lower()[:16]
        key = f"{_safe_tenant_segment(tenant_id)}/{uuid.uuid4().hex}{suffix}"
        path = self._path_for(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(content)
        return key

    async def read(self, key: str) -> bytes:
        with open(self._path_for(key), "rb") as handle:
            return handle.read()

    async def delete(self, key: str) -> None:
        try:
            os.remove(self._path_for(key))
        except FileNotFoundError:
            pass
