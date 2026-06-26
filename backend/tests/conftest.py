"""Test fixtures.

Tests run against an in-memory SQLite database (via aiosqlite) for speed and
isolation. The portable GUID/JSONB column types (app/db/types.py) make the same
models work here and on Postgres. A single shared in-memory connection is reused so
all sessions see the same schema/data within a test.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator

# Configure environment BEFORE importing app modules that read settings at import.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("MASTER_KEK", "")  # dev fallback key
# Phase 1: deterministic, network-free embeddings + isolated local storage.
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("STORAGE_LOCAL_PATH", tempfile.mkdtemp(prefix="edip-test-storage-"))
# Phase 3: deterministic, offline LLM.
os.environ.setdefault("LLM_PROVIDER", "fake")
# Phase 6: disable the shared-app rate limiter for the suite (the whole suite shares one
# client ip + app instance; the limiter is exercised in isolation in test_security.py).
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")
# Phase 7/8: pin the deployment + self-hosted knobs so a developer's local `.env`
# (e.g. one pointing LLM_BASE_URL at a real endpoint) can never leak into the test suite.
# Env vars take precedence over the .env file in pydantic-settings.
os.environ.setdefault("DEPLOYMENT_MODE", "saas")
os.environ.setdefault("LLM_BASE_URL", "")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
# The human-review/hold tests assert the gate's behavior, so pin it on here regardless of
# a developer's local `.env` (the v1 product runs with it OFF). Tests that need it off set
# it explicitly via monkeypatch.
os.environ.setdefault("ENABLE_HUMAN_REVIEW", "true")

import pytest
import pytest_asyncio
from app.db.base import Base
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def engine():
    # StaticPool + shared in-memory URI keeps one connection for the whole test.
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine, session_factory) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client wired to the app, with DB dependencies pointed at the test engine."""
    import app.db.session as db_session_module
    from app.core.deps import get_db
    from app.main import app

    # Point the audit service's independent-session factory at the test engine too.
    db_session_module.SessionLocal = session_factory

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def register_payload() -> dict[str, str]:
    return {
        "tenant_name": "Acme Legal",
        "tenant_slug": "acme-legal",
        "email": "owner@acme.com",
        "password": "correct horse battery staple",
    }


async def register_tenant(client: AsyncClient, slug: str, email: str) -> dict:
    """Helper: register a tenant+owner and return {tenant_id, headers, token}."""
    r = await client.post(
        "/auth/register",
        json={
            "tenant_name": slug.replace("-", " ").title(),
            "tenant_slug": slug,
            "email": email,
            "password": "correct horse battery staple",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["tokens"]["access_token"]
    return {
        "tenant_id": body["tenant"]["id"],
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def acme(client: AsyncClient) -> dict:
    """A registered tenant (Acme) with auth headers ready to use."""
    return await register_tenant(client, "acme-legal", "owner@acme.com")


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
