"""Async database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _async_engine_args() -> tuple[str | object, dict[str, object]]:
    """Resolve the async DB URL + connect_args for managed Postgres.

    asyncpg does not accept libpq's ``sslmode`` / ``channel_binding`` query
    parameters (psycopg/Alembic do). Managed Postgres (Neon/Supabase/RDS)
    connection strings carry these; for the asyncpg engine we:

    - translate ``sslmode`` into asyncpg's ``ssl`` connect-arg,
    - drop ``channel_binding`` (asyncpg negotiates SCRAM channel binding itself),
    - disable the prepared-statement cache, since the pooled Neon/Supabase
      endpoints sit behind PgBouncer in transaction mode (named prepared
      statements break there).

    URLs without ``sslmode`` (SQLite tests, local Postgres) are returned untouched.
    """
    url = make_url(settings.DATABASE_URL)
    connect_args: dict[str, object] = {}
    if url.drivername.endswith("asyncpg") and "sslmode" in url.query:
        query = dict(url.query)
        connect_args["ssl"] = query.pop("sslmode")
        query.pop("channel_binding", None)
        # PgBouncer transaction-pooling safety (Neon/Supabase pooled endpoints).
        connect_args["statement_cache_size"] = 0
        query["prepared_statement_cache_size"] = "0"
        url = url.set(query=query)
    return url, connect_args


_url, _connect_args = _async_engine_args()
engine = create_async_engine(
    _url,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional session.

    Commits on success, rolls back on exception, always closes.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
