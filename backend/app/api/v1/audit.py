"""Audit log read + export — admin/owner only, strictly tenant-scoped.

``/audit/logs`` returns filtered, paginated JSON. ``/audit/export`` streams the same
filtered rows as NDJSON or CSV for SIEM ingestion. The tenant filter always comes from
the authenticated principal, never a query parameter, and the export itself is audited.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_db, require_role
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import UserRole
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: AuditAction
    resource_type: str | None
    resource_id: str | None
    event_metadata: dict | None
    ip_address: str | None
    trace_id: str | None
    outcome: str | None
    created_at: datetime


def _filtered(
    tenant_id: uuid.UUID,
    *,
    action: AuditAction | None,
    actor_user_id: uuid.UUID | None,
    resource_type: str | None,
    outcome: str | None,
    start: datetime | None,
    end: datetime | None,
) -> Select:
    """Build a tenant-scoped, filtered audit query (newest first)."""
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if outcome is not None:
        stmt = stmt.where(AuditLog.outcome == outcome)
    if start is not None:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.created_at <= end)
    return stmt.order_by(AuditLog.created_at.desc())


@router.get("/logs", response_model=list[AuditLogRead])
async def list_audit_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: AuditAction | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    current: CurrentUser = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    """Return the calling tenant's audit events, newest first, with optional filters."""
    stmt = _filtered(
        current.tenant_id, action=action, actor_user_id=actor_user_id,
        resource_type=resource_type, outcome=outcome, start=start, end=end,
    )
    logs = list((await db.scalars(stmt.limit(limit).offset(offset))).all())
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.AUDIT_READ,
        actor_user_id=current.id,
        resource_type="audit_log",
        metadata={"limit": limit, "offset": offset, "returned": len(logs)},
        ip_address=client_ip(request),
    )
    return logs


def _row_dict(log: AuditLog) -> dict:
    return {
        "id": str(log.id),
        "created_at": log.created_at.isoformat(),
        "tenant_id": str(log.tenant_id),
        "actor_user_id": str(log.actor_user_id) if log.actor_user_id else None,
        "action": log.action.value,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "outcome": log.outcome,
        "ip_address": log.ip_address,
        "trace_id": log.trace_id,
        "metadata": log.event_metadata,
    }


_CSV_FIELDS = [
    "id", "created_at", "tenant_id", "actor_user_id", "action",
    "resource_type", "resource_id", "outcome", "ip_address", "trace_id",
]


@router.get("/export")
async def export_audit_logs(
    request: Request,
    fmt: str = Query(default="ndjson", pattern="^(ndjson|csv|json)$", alias="format"),
    limit: int = Query(default=10000, ge=1, le=100000),
    action: AuditAction | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    current: CurrentUser = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream filtered audit rows for SIEM ingestion (NDJSON / CSV / JSON array)."""
    stmt = _filtered(
        current.tenant_id, action=action, actor_user_id=actor_user_id,
        resource_type=resource_type, outcome=outcome, start=start, end=end,
    ).limit(limit)
    logs = list((await db.scalars(stmt)).all())
    rows = [_row_dict(log) for log in logs]

    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.AUDIT_EXPORTED,
        actor_user_id=current.id,
        resource_type="audit_log",
        metadata={"format": fmt, "returned": len(rows)},
        ip_address=client_ip(request),
        outcome="allow",
    )
    await db.commit()

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
        )
    if fmt == "json":
        return StreamingResponse(
            iter([json.dumps(rows)]), media_type="application/json"
        )
    # ndjson (default, SIEM-friendly).
    body = "".join(json.dumps(row) + "\n" for row in rows)
    return StreamingResponse(iter([body]), media_type="application/x-ndjson")
