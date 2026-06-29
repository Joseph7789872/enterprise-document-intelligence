"""Per-tenant usage counters for plan-limit enforcement (Phase D).

Synchronous ``COUNT`` queries against the tenant's own rows — cheap and exact, no separate
metering store. ``count_queries_this_period`` counts from the start of the current UTC
calendar month (the monthly-query limit window).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.query import Query
from app.models.user import User


def current_period_start(now: datetime | None = None) -> datetime:
    """Start of the current UTC calendar month — the monthly-query window boundary."""
    ref = now or datetime.now(UTC)
    return ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def count_active_users(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        or 0
    )


async def count_documents(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == tenant_id, Document.deleted_at.is_(None))
        )
        or 0
    )


async def count_queries_this_period(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Query)
            .where(
                Query.tenant_id == tenant_id,
                Query.created_at >= current_period_start(),
            )
        )
        or 0
    )


@dataclass(frozen=True)
class UsageSnapshot:
    users: int
    documents: int
    queries_this_period: int


async def snapshot(db: AsyncSession, tenant_id: uuid.UUID) -> UsageSnapshot:
    return UsageSnapshot(
        users=await count_active_users(db, tenant_id),
        documents=await count_documents(db, tenant_id),
        queries_this_period=await count_queries_this_period(db, tenant_id),
    )
