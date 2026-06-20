"""Saved objection endpoints: AE-readable objection library + manager CRUD.

Any authenticated user (AE or manager) may list the saved objections (the chat's
objection-lookup quick mode); only managers (OWNER/ADMIN) may create/update/delete them.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_current_user, get_db, require_role
from app.errors import NotFoundError
from app.models.audit_log import AuditAction
from app.models.saved_objection import SavedObjection
from app.models.user import UserRole
from app.schemas.curation import SavedObjectionCreate, SavedObjectionRead, SavedObjectionUpdate
from app.services import audit_service

router = APIRouter(prefix="/objections", tags=["objections"])

_manager = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get("", response_model=list[SavedObjectionRead])
async def list_objections(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SavedObjection]:
    """The tenant's saved objection library, ordered for the chat quick-mode list."""
    rows = await db.scalars(
        select(SavedObjection)
        .where(SavedObjection.tenant_id == current.tenant_id)
        .order_by(SavedObjection.sort_order, SavedObjection.created_at)
    )
    return list(rows.all())


@router.post("", response_model=SavedObjectionRead, status_code=status.HTTP_201_CREATED)
async def create_objection(
    body: SavedObjectionCreate,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> SavedObjection:
    objection = SavedObjection(
        tenant_id=current.tenant_id,
        label=body.label,
        prompt=body.prompt,
        sort_order=body.sort_order,
    )
    db.add(objection)
    await db.flush()
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
    return objection


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
) -> SavedObjection:
    objection = await _load_objection(db, current, objection_id)
    if body.label is not None:
        objection.label = body.label
    if body.prompt is not None:
        objection.prompt = body.prompt
    if body.sort_order is not None:
        objection.sort_order = body.sort_order
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
    return objection


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
