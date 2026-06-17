"""Local storage backend tests."""

from __future__ import annotations

import uuid

import pytest
from app.storage import StorageError, document_storage_key
from app.storage.local import LocalStorageBackend


def test_put_get_delete_roundtrip(tmp_path) -> None:
    backend = LocalStorageBackend(base_path=str(tmp_path))
    key = document_storage_key(uuid.uuid4(), uuid.uuid4())
    backend.put(key, b"encrypted-bytes")
    assert backend.get(key) == b"encrypted-bytes"
    backend.delete(key)
    with pytest.raises(StorageError):
        backend.get(key)


def test_missing_object_raises(tmp_path) -> None:
    backend = LocalStorageBackend(base_path=str(tmp_path))
    with pytest.raises(StorageError):
        backend.get("tenants/x/documents/does-not-exist")


def test_path_traversal_is_rejected(tmp_path) -> None:
    backend = LocalStorageBackend(base_path=str(tmp_path))
    with pytest.raises(StorageError):
        backend.put("../../escape", b"nope")


def test_delete_is_idempotent(tmp_path) -> None:
    backend = LocalStorageBackend(base_path=str(tmp_path))
    backend.delete("tenants/x/documents/never-existed")  # no error
