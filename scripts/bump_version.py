#!/usr/bin/env python3
"""Bump the project version in one place.

Updates the repo-root ``VERSION`` file and the ``version`` field in
``backend/pyproject.toml``, and seeds a new ``## [x.y.z]`` section under ``[Unreleased]``
in ``CHANGELOG.md``. ``app/version.py`` reads ``VERSION`` at runtime, so the app, OpenAPI,
and logs all follow automatically.

    python scripts/bump_version.py patch|minor|major
    python scripts/bump_version.py 1.2.3        # explicit version
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
PYPROJECT = ROOT / "backend" / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def _current() -> tuple[int, int, int]:
    parts = VERSION_FILE.read_text(encoding="utf-8").strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise SystemExit(f"VERSION is not semver: {VERSION_FILE.read_text()!r}")
    major, minor, patch = (int(p) for p in parts)
    return major, minor, patch


def _next(arg: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+", arg):
        return arg
    major, minor, patch = _current()
    if arg == "major":
        return f"{major + 1}.0.0"
    if arg == "minor":
        return f"{major}.{minor + 1}.0"
    if arg == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit("Usage: bump_version.py patch|minor|major|X.Y.Z")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: bump_version.py patch|minor|major|X.Y.Z")
    new = _next(sys.argv[1])

    VERSION_FILE.write_text(f"{new}\n", encoding="utf-8")

    pyproject = PYPROJECT.read_text(encoding="utf-8")
    pyproject, n = re.subn(
        r'^version = "\d+\.\d+\.\d+"', f'version = "{new}"', pyproject, count=1, flags=re.M
    )
    if n == 1:
        PYPROJECT.write_text(pyproject, encoding="utf-8")

    today = _dt.date.today().isoformat()
    changelog = CHANGELOG.read_text(encoding="utf-8")
    changelog = changelog.replace(
        "## [Unreleased]\n",
        f"## [Unreleased]\n\n## [{new}] — {today}\n",
        1,
    )
    CHANGELOG.write_text(changelog, encoding="utf-8")

    print(f"Bumped to {new}. Review CHANGELOG.md, then commit + tag v{new}.")


if __name__ == "__main__":
    main()
