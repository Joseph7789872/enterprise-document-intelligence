"""Single source of truth for the application version.

Reads the repo-root ``VERSION`` file when present (the canonical source that
``scripts/bump_version.py`` edits), falling back to installed package metadata, then a
hard-coded default. Keeping this in one place means ``main.py``/OpenAPI, logs, and any
release tooling all report the same string.
"""

from __future__ import annotations

from pathlib import Path

_FALLBACK = "0.1.0"


def _read_version() -> str:
    # backend/app/version.py → repo root is three parents up.
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("edip-backend")
        except PackageNotFoundError:
            return _FALLBACK
    except ImportError:  # pragma: no cover - importlib.metadata is stdlib on 3.11
        return _FALLBACK


__version__ = _read_version()
