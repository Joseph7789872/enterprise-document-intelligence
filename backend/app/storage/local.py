"""Local-filesystem storage backend (development / single-node)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.storage import StorageError


class LocalStorageBackend:
    """Stores objects as files under ``STORAGE_LOCAL_PATH``.

    Keys may contain ``/`` and are mapped to nested directories. Path traversal is
    prevented by rejecting any key that resolves outside the base directory.
    """

    def __init__(self, base_path: str | None = None) -> None:
        self._base = Path(base_path or settings.STORAGE_LOCAL_PATH).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        target = (self._base / key).resolve()
        if not target.is_relative_to(self._base):
            raise StorageError(f"Refusing to access key outside storage root: {key!r}")
        return target

    def put(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"Object not found: {key!r}") from exc

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)
