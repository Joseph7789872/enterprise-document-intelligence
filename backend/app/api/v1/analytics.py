"""Manager analytics — read-only, manager-only, strictly tenant-scoped (Phase E).

Mirrors the /audit endpoints: the tenant always comes from the authenticated principal
(never a query param), every read is audited, and the export reuses the same CSV pattern.
``/overview`` and ``/export`` are metadata-only; ``/low-confidence`` is the single endpoint
that decrypts question text (for manager coaching).
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_db, require_role
from app.models.audit_log import AuditAction
from app.models.user import UserRole
from app.schemas.analytics import AnalyticsOverview, LowConfidenceItem
from app.services import analytics_service, audit_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

_manager = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get("/overview", response_model=AnalyticsOverview)
async def get_overview(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverview:
    """Team activity, answer quality, and content insights over the last ``days`` days."""
    result = await analytics_service.overview(db, current.tenant_id, days=days)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.ANALYTICS_VIEWED,
        actor_user_id=current.id,
        resource_type="analytics",
        metadata={"days": result.days, "view": "overview"},
        ip_address=client_ip(request),
    )
    return result


@router.get("/low-confidence", response_model=list[LowConfidenceItem])
async def get_low_confidence(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> list[LowConfidenceItem]:
    """Recent low-confidence questions (decrypted) so a manager can spot coaching gaps."""
    items = await analytics_service.recent_low_confidence(
        db, current.tenant_id, days=days, limit=limit
    )
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.ANALYTICS_VIEWED,
        actor_user_id=current.id,
        resource_type="analytics",
        metadata={"days": days, "view": "low_confidence", "returned": len(items)},
        ip_address=client_ip(request),
    )
    return items


_CSV_FIELDS = ["email", "role", "query_count", "answered_count", "avg_confidence", "last_active"]


@router.get("/export")
async def export_rep_activity(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the per-rep activity table as CSV."""
    result = await analytics_service.overview(db, current.tenant_id, days=days)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.ANALYTICS_EXPORTED,
        actor_user_id=current.id,
        resource_type="analytics",
        metadata={"days": result.days, "reps": len(result.rep_activity)},
        ip_address=client_ip(request),
        outcome="allow",
    )
    await db.commit()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for r in result.rep_activity:
        writer.writerow(
            {
                "email": r.email,
                "role": r.role,
                "query_count": r.query_count,
                "answered_count": r.answered_count,
                "avg_confidence": r.avg_confidence if r.avg_confidence is not None else "",
                "last_active": r.last_active.isoformat() if r.last_active else "",
            }
        )
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rep_activity.csv"},
    )
