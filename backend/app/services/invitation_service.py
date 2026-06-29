"""Invitations — invite a teammate by email; they accept by setting a password (Phase D).

Token design mirrors API keys: the emailed token is ``{invitation_id}.{secret}``; only
``hash_password(secret)`` is stored, so the id gives an O(1) lookup and the secret is
verified with ``verify_password`` (the plaintext lives only in the email). Seat limits are
enforced via ``billing_service`` so an invite can't exceed the plan.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.errors import AppError, ConflictError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.invitation import Invitation, InvitationStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.auth import TokenPair
from app.services import audit_service, billing_service
from app.services.auth_service import _issue_tokens


class InvalidInvitationError(AppError):
    """The invitation token is unknown, already used, revoked, or expired."""

    status_code = 400
    message = "This invitation link is invalid or has expired."


def _new_token(invitation_id: uuid.UUID) -> tuple[str, str]:
    """Return ``(raw_token, secret)`` — raw is ``{id}.{secret}`` for the emailed link."""
    secret = secrets.token_urlsafe(32)
    return f"{invitation_id.hex}.{secret}", secret


def _is_expired(expires_at: datetime) -> bool:
    """Compare safely: SQLite returns tz-naive datetimes, so treat naive values as UTC."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < datetime.now(UTC)


async def create_invitation(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    inviter_id: uuid.UUID,
    email: str,
    role: UserRole,
) -> tuple[Invitation, str]:
    """Create a PENDING invite + return the one-time raw token. Seat-limit + dup checks."""
    email = email.lower()
    await billing_service.enforce_quota(db, tenant_id, "seats")

    existing_user = await db.scalar(
        select(User).where(
            User.tenant_id == tenant_id, User.email == email, User.deleted_at.is_(None)
        )
    )
    if existing_user is not None:
        raise ConflictError("A user with that email already exists in this tenant.")

    existing_invite = await db.scalar(
        select(Invitation).where(
            Invitation.tenant_id == tenant_id,
            Invitation.email == email,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    if existing_invite is not None:
        raise ConflictError("An invitation for that email is already pending.")

    invitation = Invitation(
        tenant_id=tenant_id,
        email=email,
        role=role,
        token_hash="",  # set below once we have the id
        expires_at=datetime.now(UTC) + timedelta(hours=settings.INVITE_TOKEN_TTL_HOURS),
        status=InvitationStatus.PENDING,
        invited_by_user_id=inviter_id,
    )
    db.add(invitation)
    await db.flush()  # assign invitation.id

    raw_token, secret = _new_token(invitation.id)
    invitation.token_hash = hash_password(secret)
    await db.flush()
    return invitation, raw_token


async def accept_invitation(
    db: AsyncSession, *, raw_token: str, password: str
) -> tuple[User, Tenant, TokenPair]:
    """Validate the token, create the active user, and return tokens for auto-login."""
    invite_id_hex, _, secret = raw_token.partition(".")
    if not invite_id_hex or not secret:
        raise InvalidInvitationError()
    try:
        invite_id = uuid.UUID(hex=invite_id_hex)
    except ValueError as exc:
        raise InvalidInvitationError() from exc

    invitation = await db.get(Invitation, invite_id)
    if (
        invitation is None
        or invitation.status != InvitationStatus.PENDING
        or _is_expired(invitation.expires_at)
        or not verify_password(secret, invitation.token_hash)
    ):
        raise InvalidInvitationError()

    # Guard against a race where the email got taken between invite and accept.
    existing_user = await db.scalar(
        select(User).where(
            User.tenant_id == invitation.tenant_id,
            User.email == invitation.email,
            User.deleted_at.is_(None),
        )
    )
    if existing_user is not None:
        raise ConflictError("A user with that email already exists in this tenant.")

    user = User(
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        hashed_password=hash_password(password),
        role=invitation.role,
        is_active=True,
    )
    db.add(user)
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(UTC)
    await db.flush()

    tenant = await db.get(Tenant, invitation.tenant_id)
    if tenant is None:  # FK guarantees this, but keep the type checker + runtime honest
        raise InvalidInvitationError()
    await audit_service.write_event(
        db,
        tenant_id=invitation.tenant_id,
        action=AuditAction.INVITE_ACCEPTED,
        actor_user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        metadata={"invitation_id": str(invitation.id), "role": user.role.value},
    )
    return user, tenant, _issue_tokens(user)


async def list_pending(db: AsyncSession, tenant_id: uuid.UUID) -> list[Invitation]:
    rows = await db.scalars(
        select(Invitation)
        .where(
            Invitation.tenant_id == tenant_id,
            Invitation.status == InvitationStatus.PENDING,
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(rows.all())


async def revoke(db: AsyncSession, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID) -> Invitation:
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.tenant_id != tenant_id:
        raise NotFoundError("Invitation not found.")
    invitation.status = InvitationStatus.REVOKED
    await db.flush()
    return invitation
