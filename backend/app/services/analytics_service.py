"""Manager analytics — read-only aggregation over existing tables (Phase E).

One windowed fetch + Python aggregation (mirrors usage_service's count pattern but for a
whole dashboard). Date bucketing is done in Python from fetched ``created_at`` values — no
Postgres-only ``date_trunc``/SQLite-only ``strftime`` — so it's portable across both. The
overview path selects metadata columns only and never decrypts; the sole decryption path is
:func:`recent_low_confidence`. At a sales team's scale this is comfortably fast; it can move
to SQL ``GROUP BY`` if volume ever demands it.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_str
from app.models.document import Document
from app.models.query import Query, QueryStatus
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsOverview,
    AnswerQuality,
    CitedDocument,
    ContentInsights,
    LowConfidenceItem,
    RepActivity,
    TrendPoint,
    UncitedDocument,
    UploadsByType,
)

_MOST_CITED_LIMIT = 10
_UNCITED_LIMIT = 50


def clamp_days(days: int) -> int:
    return max(1, min(days, 365))


def _window(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=clamp_days(days))


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns tz-naive datetimes — treat naive values as UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _day(dt: datetime) -> date:
    return _as_utc(dt).date()


async def overview(db: AsyncSession, tenant_id: uuid.UUID, *, days: int) -> AnalyticsOverview:
    days = clamp_days(days)
    since = _window(days)

    # Metadata only — no *_encrypted columns are read here.
    rows = (
        await db.execute(
            select(
                Query.user_id, Query.status, Query.confidence, Query.citations, Query.created_at
            ).where(Query.tenant_id == tenant_id, Query.created_at >= since)
        )
    ).all()

    users = list(
        (
            await db.scalars(
                select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
            )
        ).all()
    )
    documents = list(
        (
            await db.scalars(
                select(Document).where(
                    Document.tenant_id == tenant_id, Document.deleted_at.is_(None)
                )
            )
        ).all()
    )

    threshold = settings.CONFIDENCE_THRESHOLD

    # ── Per-rep aggregation ──────────────────────────────────────────────────────────
    agg: dict[uuid.UUID, dict] = defaultdict(
        lambda: {"count": 0, "answered": 0, "conf_sum": 0.0, "conf_n": 0, "last": None}
    )
    # ── Trend, quality, citations (single pass over the window's queries) ─────────────
    per_day: dict[date, int] = defaultdict(int)
    total = low_conf = pending = rejected = with_cites = 0
    conf_sum = 0.0
    conf_n = 0
    cite_counts: dict[str, int] = defaultdict(int)
    cite_filename: dict[str, str] = {}

    for user_id, status, confidence, citations, created_at in rows:
        total += 1
        per_day[_day(created_at)] += 1

        a = agg[user_id]
        a["count"] += 1
        if status == QueryStatus.COMPLETED:
            a["answered"] += 1
        if a["last"] is None or _as_utc(created_at) > a["last"]:
            a["last"] = _as_utc(created_at)
        if confidence is not None:
            a["conf_sum"] += confidence
            a["conf_n"] += 1
            conf_sum += confidence
            conf_n += 1
            if confidence < threshold:
                low_conf += 1
        if status == QueryStatus.PENDING_APPROVAL:
            pending += 1
        if status == QueryStatus.REJECTED:
            rejected += 1
        if citations:
            with_cites += 1
            for c in citations:
                doc_id = str(c.get("document_id"))
                cite_counts[doc_id] += 1
                cite_filename.setdefault(doc_id, c.get("filename") or doc_id)

    active_ids = set(agg)  # snapshot before .get() below (defaultdict would auto-insert)
    rep_activity = []
    for u in users:
        stats = agg.get(u.id)
        rep_activity.append(
            RepActivity(
                user_id=u.id,
                email=u.email,
                role=u.role.value,
                query_count=stats["count"] if stats else 0,
                answered_count=stats["answered"] if stats else 0,
                avg_confidence=(
                    round(stats["conf_sum"] / stats["conf_n"], 3)
                    if stats and stats["conf_n"]
                    else None
                ),
                last_active=stats["last"] if stats else None,
                active=u.id in active_ids,
            )
        )
    rep_activity.sort(key=lambda r: (-r.query_count, r.email))
    active_reps = len(active_ids)

    # ── Zero-filled daily trend across the whole window ──────────────────────────────
    start_day = since.date()
    end_day = datetime.now(UTC).date()
    trend: list[TrendPoint] = []
    cursor = start_day
    while cursor <= end_day:
        trend.append(TrendPoint(date=cursor.isoformat(), count=per_day.get(cursor, 0)))
        cursor += timedelta(days=1)

    answer_quality = AnswerQuality(
        total=total,
        avg_confidence=round(conf_sum / conf_n, 3) if conf_n else None,
        low_confidence=low_conf,
        pending_approval=pending,
        rejected=rejected,
        with_citations=with_cites,
        citation_coverage_pct=round(with_cites / total * 100, 1) if total else 0.0,
    )

    # ── Content insights ─────────────────────────────────────────────────────────────
    most_cited = sorted(cite_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_MOST_CITED_LIMIT]
    cited_ids = set(cite_counts)
    uncited = [
        UncitedDocument(
            document_id=str(d.id), filename=d.filename, content_type=d.content_type.value
        )
        for d in documents
        if str(d.id) not in cited_ids
    ][:_UNCITED_LIMIT]
    uploads: dict[str, int] = defaultdict(int)
    for d in documents:
        if _as_utc(d.created_at) >= since:
            uploads[d.content_type.value] += 1

    content_insights = ContentInsights(
        most_cited=[
            CitedDocument(document_id=did, filename=cite_filename.get(did, did), citation_count=n)
            for did, n in most_cited
        ],
        uncited_documents=uncited,
        uploads_by_type=[
            UploadsByType(content_type=ct, count=n) for ct, n in sorted(uploads.items())
        ],
    )

    return AnalyticsOverview(
        days=days,
        since=since,
        total_queries=total,
        active_reps=active_reps,
        rep_activity=rep_activity,
        query_trend=trend,
        answer_quality=answer_quality,
        content_insights=content_insights,
    )


async def recent_low_confidence(
    db: AsyncSession, tenant_id: uuid.UUID, *, days: int, limit: int
) -> list[LowConfidenceItem]:
    """The only decrypting path: recent low-confidence questions for manager coaching."""
    since = _window(days)
    limit = max(1, min(limit, 100))
    threshold = settings.CONFIDENCE_THRESHOLD

    rows = list(
        (
            await db.scalars(
                select(Query)
                .where(
                    Query.tenant_id == tenant_id,
                    Query.created_at >= since,
                    Query.status == QueryStatus.COMPLETED,
                    Query.confidence.is_not(None),
                    Query.confidence < threshold,
                )
                .order_by(Query.created_at.desc())
                .limit(limit)
            )
        ).all()
    )

    email_rows = (
        await db.execute(select(User.id, User.email).where(User.tenant_id == tenant_id))
    ).all()
    emails: dict[uuid.UUID, str] = {}
    for uid, email in email_rows:
        emails[uid] = email
    return [
        LowConfidenceItem(
            query_id=q.id,
            user_email=emails.get(q.user_id, "(unknown)"),
            confidence=q.confidence,
            question=decrypt_str(q.question_encrypted),
            created_at=q.created_at,
        )
        for q in rows
    ]
