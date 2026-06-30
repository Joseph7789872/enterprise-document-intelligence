"""Invitation API schemas (Phase D)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.invitation import InvitationStatus
from app.models.user import UserRole


class InvitationCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.MEMBER


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime


class InvitationCreated(InvitationRead):
    """Returned when an invite is created or its key is regenerated. Includes the one-time
    invite key (shared out-of-band via Slack/Teams) plus the workspace identifier the
    teammate needs to join. The raw key is only ever exposed here, never on the list
    endpoint."""

    invite_key: str
    tenant_slug: str


class AcceptInviteResponse(BaseModel):
    """Returned on successful accept — mirrors RegisterResponse so the client logs in."""

    user_id: uuid.UUID = Field(...)
    tenant_id: uuid.UUID
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token_type label, not a secret
