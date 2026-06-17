"""Security hardening tests: response headers + rate limiter."""

from __future__ import annotations

import pytest
from app.core.middleware import RateLimitMiddleware
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_security_headers_present(client) -> None:
    r = await client.get("/health")
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Strict-Transport-Security" in r.headers
    assert "Permissions-Policy" in r.headers
    # The API gets the strict CSP (JSON only).
    assert r.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.asyncio
async def test_docs_get_relaxed_csp(client) -> None:
    # The interactive docs need a Swagger-compatible CSP so /docs renders.
    r = await client.get("/docs")
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in csp
    assert "default-src 'none'" not in csp


@pytest.mark.asyncio
async def test_rate_limiter_returns_429_past_threshold() -> None:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=2)

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        assert (await ac.get("/ping")).status_code == 200
        assert (await ac.get("/ping")).status_code == 200
        third = await ac.get("/ping")
        assert third.status_code == 429
        assert "Rate limit" in third.json()["detail"]
