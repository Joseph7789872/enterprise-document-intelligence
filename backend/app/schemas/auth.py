"""Authentication API schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.schemas.tenant import TenantRead
from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    """Bootstrap a new tenant together with its first (owner) user."""

    tenant_name: str = Field(min_length=1, max_length=255)
    tenant_slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token_type label, not a secret


class RegisterResponse(BaseModel):
    tenant: TenantRead
    user: UserRead
    tokens: TokenPair


# ── Phase D: invitations + password reset ──────────────────────────────────────────
class AcceptInviteRequest(BaseModel):
    """Accept an emailed invitation by choosing a password."""

    token: str = Field(min_length=1)
    password: str = Field(min_length=12, max_length=128)


class ForgotPasswordRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=100)
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=128)
