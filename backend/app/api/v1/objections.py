"""Saved objection endpoints: AE-readable objection library + manager CRUD.

Any authenticated user (AE or manager) may list the saved objections (the chat's
objection-lookup quick mode); only managers (OWNER/ADMIN) may create/update/delete them.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_current_user, get_db, require_role
from app.errors import NotFoundError
from app.models.audit_log import AuditAction
from app.models.objection_segment import ObjectionSegment
from app.models.saved_objection import SavedObjection
from app.models.user import UserRole
from app.schemas.curation import SavedObjectionCreate, SavedObjectionRead, SavedObjectionUpdate
from app.services import audit_service, segment_service

router = APIRouter(prefix="/objections", tags=["objections"])

_manager = require_role(UserRole.OWNER, UserRole.ADMIN)


def _to_read(objection: SavedObjection, segment_ids: list[uuid.UUID]) -> SavedObjectionRead:
    return SavedObjectionRead(
        id=objection.id,
        label=objection.label,
        prompt=objection.prompt,
        sort_order=objection.sort_order,
        created_at=objection.created_at,
        segment_ids=segment_ids,
    )


@router.get("", response_model=list[SavedObjectionRead])
async def list_objections(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    segment_id: uuid.UUID | None = Query(default=None),
) -> list[SavedObjectionRead]:
    """The tenant's saved objection library, ordered for the chat quick-mode list.

    Pass ``segment_id`` to return only objections tagged with that segment (the AE
    "objections for [segment]" filter).
    """
    stmt = (
        select(SavedObjection)
        .where(SavedObjection.tenant_id == current.tenant_id)
        .order_by(SavedObjection.sort_order, SavedObjection.created_at)
    )
    if segment_id is not None:
        stmt = stmt.join(
            ObjectionSegment, ObjectionSegment.objection_id == SavedObjection.id
        ).where(ObjectionSegment.segment_id == segment_id)
    rows = (await db.scalars(stmt)).all()
    tags = await segment_service.segments_for_objections(
        db, tenant_id=current.tenant_id, objection_ids=[o.id for o in rows]
    )
    return [_to_read(o, tags.get(o.id, [])) for o in rows]


@router.post("", response_model=SavedObjectionRead, status_code=status.HTTP_201_CREATED)
async def create_objection(
    body: SavedObjectionCreate,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> SavedObjectionRead:
    objection = SavedObjection(
        tenant_id=current.tenant_id,
        label=body.label,
        prompt=body.prompt,
        sort_order=body.sort_order,
    )
    db.add(objection)
    await db.flush()
    segment_ids: list[uuid.UUID] = []
    if body.segment_ids is not None:
        segment_ids = await segment_service.replace_objection_segments(
            db, tenant_id=current.tenant_id, objection_id=objection.id, segment_ids=body.segment_ids
        )
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.OBJECTION_CREATED,
        actor_user_id=current.id,
        resource_type="saved_objection",
        resource_id=str(objection.id),
        ip_address=client_ip(request),
        outcome="allow",
    )
    return _to_read(objection, segment_ids)


async def _load_objection(
    db: AsyncSession, current: CurrentUser, objection_id: uuid.UUID
) -> SavedObjection:
    objection = await db.get(SavedObjection, objection_id)
    if objection is None or objection.tenant_id != current.tenant_id:
        raise NotFoundError("Saved objection not found.")
    return objection


@router.patch("/{objection_id}", response_model=SavedObjectionRead)
async def update_objection(
    objection_id: uuid.UUID,
    body: SavedObjectionUpdate,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> SavedObjectionRead:
    objection = await _load_objection(db, current, objection_id)
    if body.label is not None:
        objection.label = body.label
    if body.prompt is not None:
        objection.prompt = body.prompt
    if body.sort_order is not None:
        objection.sort_order = body.sort_order
    if body.segment_ids is not None:
        await segment_service.replace_objection_segments(
            db, tenant_id=current.tenant_id, objection_id=objection.id, segment_ids=body.segment_ids
        )
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.OBJECTION_UPDATED,
        actor_user_id=current.id,
        resource_type="saved_objection",
        resource_id=str(objection.id),
        ip_address=client_ip(request),
        outcome="allow",
    )
    tags = await segment_service.segments_for_objections(
        db, tenant_id=current.tenant_id, objection_ids=[objection.id]
    )
    return _to_read(objection, tags.get(objection.id, []))


@router.delete("/{objection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_objection(
    objection_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    objection = await _load_objection(db, current, objection_id)
    await db.delete(objection)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.OBJECTION_DELETED,
        actor_user_id=current.id,
        resource_type="saved_objection",
        resource_id=str(objection_id),
        ip_address=client_ip(request),
        outcome="allow",
    )
