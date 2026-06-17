"""Schemas for ACL grants, groups, and admin user management."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.document_access_control import PrincipalType
from app.models.group import GroupType
from app.models.user import UserRole
from app.services.authz import Permission


# ── ACL grants ───────────────────────────────────────────────────────────────────
class ACLGrantCreate(BaseModel):
    principal_type: PrincipalType
    principal_id: uuid.UUID
    permissions: list[Permission] = Field(min_length=1)


class ACLGrantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    principal_type: PrincipalType
    principal_id: uuid.UUID
    permissions: list[str]
    granted_by_user_id: uuid.UUID
    created_at: datetime


# ── Groups ───────────────────────────────────────────────────────────────────────
class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    group_type: GroupType = GroupType.CUSTOM
    description: str | None = Field(default=None, max_length=500)


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    group_type: GroupType
    description: str | None
    created_at: datetime


class GroupMemberAdd(BaseModel):
    user_id: uuid.UUID


# ── Admin user management ──────────────────────────────────────────────────────────
class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: UserRole = UserRole.MEMBER


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
