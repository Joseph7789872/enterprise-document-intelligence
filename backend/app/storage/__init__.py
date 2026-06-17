"""Object storage abstraction for (envelope-encrypted) document bytes.

Phase 1 ships a local-filesystem backend for development and an S3/MinIO backend
for production, selected by ``settings.STORAGE_BACKEND``. Callers always store
already-encrypted bytes — encryption is the ingestion layer's responsibility, not
storage's, so the backend can be swapped freely.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Protocol

from app.core.config import settings


class StorageBackend(Protocol):
    """Minimal object-storage interface."""

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class StorageError(Exception):
    """Raised on storage I/O failures (missing object, backend error)."""


def document_storage_key(tenant_id: uuid.UUID, document_id: uuid.UUID) -> str:
    """Canonical key for a document's encrypted bytes."""
    return f"tenants/{tenant_id}/documents/{document_id}"


@lru_cache
def get_storage() -> StorageBackend:
    """Return the configured storage backend (cached per process)."""
    if settings.STORAGE_BACKEND == "s3":
        from app.storage.s3 import S3StorageBackend

        return S3StorageBackend()
    from app.storage.local import LocalStorageBackend

    return LocalStorageBackend()
