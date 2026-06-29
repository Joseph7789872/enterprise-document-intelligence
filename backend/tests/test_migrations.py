"""Migration smoke test — the only test that exercises Alembic itself.

The suite builds schema via ``Base.metadata.create_all``; migrations run only in real
deployments. This guards their SQLite-compatibility (notably the 0009 FK-guard fix and the
Phase B revisions) by round-tripping the whole chain on a temp SQLite file.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from app.core.config import settings

_BACKEND = Path(__file__).resolve().parents[1]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "alembic"))
    return cfg


def test_migrations_roundtrip_on_sqlite(tmp_path, monkeypatch) -> None:
    """upgrade head → downgrade base → upgrade head must all succeed on SQLite."""
    db_path = tmp_path / "migrations.db"
    # env.py derives the (sync) URL from settings.DATABASE_URL at run time.
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config(db_path)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
