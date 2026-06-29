"""Admin endpoints: user and group management (OWNER/ADMIN only, tenant-scoped).

Every resource and principal is constrained to the caller's tenant; there is no way to
touch another tenant's users or groups. All mutations are audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_db, require_role
from app.core.security import hash_password
from app.errors import ConflictError, NotFoundError
from app.models.api_key import ApiKey
from app.models.audit_log import AuditAction
from app.models.group import Group
from app.models.group_membership import GroupMembership
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.acl import (
    AdminUserCreate,
    AdminUserUpdate,
    GroupCreate,
    GroupMemberAdd,
    GroupRead,
)
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.schemas.templates import (
    TemplateApplyRequest,
    TemplateApplyResponse,
    TemplateBucket,
    TemplateInfo,
)
from app.schemas.tenant import TenantSettings, TenantSettingsUpdate
from app.schemas.user import UserRead
from app.services import api_key_service, audit_service, template_service
from app.services.templates_data import TEMPLATES

router = APIRouter(prefix="/admin", tags=["admin"])

_admin = require_role(UserRole.OWNER, UserRole.ADMIN)


# ── Users ──────────────────────────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserRead])
async def list_users(
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    rows = await db.scalars(
        select(User)
        .where(User.tenant_id == current.tenant_id, User.deleted_at.is_(None))
        .order_by(User.created_at.desc())
    )
    return list(rows.all())


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserCreate,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    existing = await db.scalar(
        select(User).where(
            User.tenant_id == current.tenant_id, User.email == body.email.lower()
        )
    )
    if existing is not None:
        raise ConflictError("A user with that email already exists in this tenant.")

    user = User(
        tenant_id=current.tenant_id,
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.USER_CREATED,
        actor_user_id=current.id,
        resource_type="user",
        resource_id=str(user.id),
        metadata={"role": user.role.value},
        ip_address=client_ip(request),
        outcome="allow",
    )
    return user


async def _load_tenant_user(db: AsyncSession, current: CurrentUser, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != current.tenant_id or user.deleted_at is not None:
        raise NotFoundError("User not found.")
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _load_tenant_user(db, current, user_id)
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.USER_UPDATED,
        actor_user_id=current.id,
        resource_type="user",
        resource_id=str(user.id),
        metadata={"role": user.role.value, "is_active": user.is_active},
        ip_address=client_ip(request),
        outcome="allow",
    )
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await _load_tenant_user(db, current, user_id)
    user.is_active = False
    user.deleted_at = datetime.now(UTC)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.USER_DEACTIVATED,
        actor_user_id=current.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=client_ip(request),
        outcome="allow",
    )


# ── Groups ─────────────────────────────────────────────────────────────────────────
@router.get("/groups", response_model=list[GroupRead])
async def list_groups(
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Group]:
    rows = await db.scalars(
        select(Group).where(Group.tenant_id == current.tenant_id).order_by(Group.name)
    )
    return list(rows.all())


@router.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> Group:
    existing = await db.scalar(
        select(Group).where(Group.tenant_id == current.tenant_id, Group.name == body.name)
    )
    if existing is not None:
        raise ConflictError("A group with that name already exists.")
    group = Group(
        tenant_id=current.tenant_id,
        name=body.name,
        group_type=body.group_type,
        description=body.description,
    )
    db.add(group)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.GROUP_CREATED,
        actor_user_id=current.id,
        resource_type="group",
        resource_id=str(group.id),
        metadata={"name": group.name, "group_type": group.group_type.value},
        ip_address=client_ip(request),
        outcome="allow",
    )
    return group


async def _load_tenant_group(db: AsyncSession, current: CurrentUser, group_id: uuid.UUID) -> Group:
    group = await db.get(Group, group_id)
    if group is None or group.tenant_id != current.tenant_id:
        raise NotFoundError("Group not found.")
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    group = await _load_tenant_group(db, current, group_id)
    await db.delete(group)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.GROUP_DELETED,
        actor_user_id=current.id,
        resource_type="group",
        resource_id=str(group_id),
        ip_address=client_ip(request),
        outcome="allow",
    )


@router.post("/groups/{group_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_group_member(
    group_id: uuid.UUID,
    body: GroupMemberAdd,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    group = await _load_tenant_group(db, current, group_id)
    member = await _load_tenant_user(db, current, body.user_id)

    existing = await db.scalar(
        select(GroupMembership).where(
            GroupMembership.group_id == group.id, GroupMembership.user_id == member.id
        )
    )
    if existing is not None:
        return  # idempotent

    db.add(
        GroupMembership(tenant_id=current.tenant_id, group_id=group.id, user_id=member.id)
    )
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.GROUP_MEMBER_ADDED,
        actor_user_id=current.id,
        resource_type="group",
        resource_id=str(group.id),
        metadata={"user_id": str(member.id)},
        ip_address=client_ip(request),
        outcome="allow",
    )


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    group = await _load_tenant_group(db, current, group_id)
    membership = await db.scalar(
        select(GroupMembership).where(
            GroupMembership.tenant_id == current.tenant_id,
            GroupMembership.group_id == group.id,
            GroupMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise NotFoundError("Membership not found.")
    await db.delete(membership)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.GROUP_MEMBER_REMOVED,
        actor_user_id=current.id,
        resource_type="group",
        resource_id=str(group.id),
        metadata={"user_id": str(user_id)},
        ip_address=client_ip(request),
        outcome="allow",
    )


# ── API keys (Phase 6) ─────────────────────────────────────────────────────────────
@router.get("/api-keys", response_model=list[ApiKeyRead])
async def list_api_keys(
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKey]:
    rows = await db.scalars(
        select(ApiKey)
        .where(ApiKey.tenant_id == current.tenant_id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(rows.all())


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    # The key acts as a chosen in-tenant user (default: the creating admin).
    acts_as = body.user_id or current.id
    if acts_as != current.id:
        await _load_tenant_user(db, current, acts_as)

    api_key, full_key = await api_key_service.issue(
        db,
        tenant_id=current.tenant_id,
        user_id=acts_as,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.API_KEY_CREATED,
        actor_user_id=current.id,
        resource_type="api_key",
        resource_id=str(api_key.id),
        metadata={"name": api_key.name, "acts_as": str(acts_as), "scopes": api_key.scopes},
        ip_address=client_ip(request),
        outcome="allow",
    )
    # The plaintext key is returned exactly once.
    fields = ApiKeyRead.model_validate(api_key).model_dump()
    return ApiKeyCreated.model_validate({**fields, "key": full_key})


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    api_key = await db.get(ApiKey, api_key_id)
    if api_key is None or api_key.tenant_id != current.tenant_id:
        raise NotFoundError("API key not found.")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.API_KEY_REVOKED,
        actor_user_id=current.id,
        resource_type="api_key",
        resource_id=str(api_key.id),
        ip_address=client_ip(request),
        outcome="allow",
    )


# ── Tenant settings (LLM routing policy, Phase 7) ────────────────────────────────────
@router.get("/tenant/settings", response_model=TenantSettings)
async def get_tenant_settings(
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantSettings:
    """Return this tenant's effective LLM routing policy (defaults when unset)."""
    tenant = await db.get(Tenant, current.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    return TenantSettings.from_raw(tenant.settings)


@router.put("/tenant/settings", response_model=TenantSettings)
async def update_tenant_settings(
    body: TenantSettingsUpdate,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantSettings:
    """Replace this tenant's LLM routing policy. Tenant-scoped + audited."""
    tenant = await db.get(Tenant, current.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    settings_obj = TenantSettings.model_validate(body.model_dump())
    tenant.settings = settings_obj.model_dump()
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.TENANT_SETTINGS_UPDATED,
        actor_user_id=current.id,
        resource_type="tenant",
        resource_id=str(current.tenant_id),
        metadata=settings_obj.model_dump(),
        ip_address=client_ip(request),
        outcome="allow",
    )
    return settings_obj


# ── Starter templates (Phase C) ──────────────────────────────────────────────────────
@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates(
    current: CurrentUser = Depends(_admin),
) -> list[TemplateInfo]:
    """Available starter templates a manager can apply to seed initial content."""
    return [
        TemplateInfo(
            key=t.key,
            name=t.name,
            description=t.description,
            segment_count=len(t.segments),
            ramp_count=len(t.ramp_topics),
            objection_count=len(t.objections),
        )
        for t in TEMPLATES.values()
    ]


@router.post("/templates/apply", response_model=TemplateApplyResponse)
async def apply_template(
    body: TemplateApplyRequest,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> TemplateApplyResponse:
    """Seed segments + ramp topics + objections from a starter template.

    Idempotent: existing names/titles/labels are skipped (never duplicated)."""
    result = await template_service.apply_template(
        db, tenant_id=current.tenant_id, template_key=body.template_key
    )
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.TEMPLATE_APPLIED,
        actor_user_id=current.id,
        resource_type="template",
        resource_id=body.template_key,
        metadata={
            "segments_created": len(result.segments.created),
            "ramp_created": len(result.ramp_topics.created),
            "objections_created": len(result.objections.created),
        },
        ip_address=client_ip(request),
        outcome="allow",
    )
    return TemplateApplyResponse(
        template_key=result.template_key,
        segments=TemplateBucket(created=result.segments.created, skipped=result.segments.skipped),
        ramp_topics=TemplateBucket(
            created=result.ramp_topics.created, skipped=result.ramp_topics.skipped
        ),
        objections=TemplateBucket(
            created=result.objections.created, skipped=result.objections.skipped
        ),
    )
