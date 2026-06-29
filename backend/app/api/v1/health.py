"""Health / readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — process is up."""
    return {"status": "ok"}


@router.get("/capabilities")
async def capabilities() -> dict[str, bool]:
    """Client-visible feature flags so the UI can hide gated surfaces (connectors,
    billing) instead of rendering cards whose actions 404. Unauthenticated and
    deliberately limited to UI-relevant booleans — no secrets or enterprise internals."""
    return {
        "connectors": settings.ENABLE_CONNECTORS,
        "billing": settings.ENABLE_BILLING,
        "signup": settings.ENABLE_SIGNUP,
    }


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Readiness probe — dependencies (DB) reachable."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
