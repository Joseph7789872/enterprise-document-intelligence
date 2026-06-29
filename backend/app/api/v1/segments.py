"""Segment endpoints: AE-readable ICP/segment list + manager CRUD.

Any authenticated user (AE or manager) may list the tenant's segments (to drive the
"objections for [segment]" filter); only managers (OWNER/ADMIN) may create/update/delete.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_current_user, get_db, require_role
from app.errors import ConflictError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.segment import Segment
from app.models.user import UserRole
from app.schemas.segment import SegmentCreate, SegmentRead, SegmentUpdate
from app.services import audit_service

router = APIRouter(prefix="/segments", tags=["segments"])

_manager = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get("", response_model=list[SegmentRead])
async def list_segments(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Segment]:
    """The tenant's segment list, ordered for selectors and filters."""
    rows = await db.scalars(
        select(Segment)
        .where(Segment.tenant_id == current.tenant_id)
        .order_by(Segment.sort_order, Segment.created_at)
    )
    return list(rows.all())


async def _ensure_unique_name(
    db: AsyncSession, current: CurrentUser, name: str, *, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = select(Segment.id).where(Segment.tenant_id == current.tenant_id, Segment.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Segment.id != exclude_id)
    if (await db.scalars(stmt)).first() is not None:
        raise ConflictError(f"A segment named '{name}' already exists.")


@router.post("", response_model=SegmentRead, status_code=status.HTTP_201_CREATED)
async def create_segment(
    body: SegmentCreate,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> Segment:
    await _ensure_unique_name(db, current, body.name)
    segment = Segment(tenant_id=current.tenant_id, name=body.name, sort_order=body.sort_order)
    db.add(segment)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.SEGMENT_CREATED,
        actor_user_id=current.id,
        resource_type="segment",
        resource_id=str(segment.id),
        ip_address=client_ip(request),
        outcome="allow",
    )
    return segment


async def _load_segment(db: AsyncSession, current: CurrentUser, segment_id: uuid.UUID) -> Segment:
    segment = await db.get(Segment, segment_id)
    if segment is None or segment.tenant_id != current.tenant_id:
        raise NotFoundError("Segment not found.")
    return segment


@router.patch("/{segment_id}", response_model=SegmentRead)
async def update_segment(
    segment_id: uuid.UUID,
    body: SegmentUpdate,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> Segment:
    segment = await _load_segment(db, current, segment_id)
    if body.name is not None:
        await _ensure_unique_name(db, current, body.name, exclude_id=segment.id)
        segment.name = body.name
    if body.sort_order is not None:
        segment.sort_order = body.sort_order
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.SEGMENT_UPDATED,
        actor_user_id=current.id,
        resource_type="segment",
        resource_id=str(segment.id),
        ip_address=client_ip(request),
        outcome="allow",
    )
    return segment


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    segment = await _load_segment(db, current, segment_id)
    # Join rows (document_segments / objection_segments) cascade-delete via FK.
    await db.delete(segment)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.SEGMENT_DELETED,
        actor_user_id=current.id,
        resource_type="segment",
        resource_id=str(segment_id),
        ip_address=client_ip(request),
        outcome="allow",
    )
