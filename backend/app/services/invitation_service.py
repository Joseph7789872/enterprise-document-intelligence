"""Invitations — invite a teammate; they join with a shareable secret key (Phase D).

The manager creates an invite and gets a short, readable **invite key** (like an API key)
to send the teammate out-of-band (Slack, Teams, etc.). The teammate joins by entering the
workspace identifier, their email, a password, and the key. Only ``hash_password(key)`` is
stored; the plaintext key is shown once at creation/regeneration and verified with
``verify_password``. The pending invite is located by ``(tenant, email)``. Seat limits are
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


# Unambiguous alphabet (Crockford-style: no 0/O/1/I to avoid transcription errors when a
# teammate types the key by hand). 20 chars → ~100 bits of entropy.
_KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_KEY_LEN = 20
_KEY_GROUP = 5


def _normalize_key(key: str) -> str:
    """Canonicalize a user-entered key: uppercase, drop dashes/spaces and any stray chars."""
    return "".join(c for c in key.upper() if c in _KEY_ALPHABET)


def _new_invite_key() -> tuple[str, str]:
    """Return ``(display_key, normalized)`` — display is grouped (e.g. ABCDE-FGHJK-…) for
    readability; the normalized (dash-free) form is what gets hashed and verified."""
    raw = "".join(secrets.choice(_KEY_ALPHABET) for _ in range(_KEY_LEN))
    display = "-".join(raw[i : i + _KEY_GROUP] for i in range(0, _KEY_LEN, _KEY_GROUP))
    return display, raw


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

    display_key, normalized = _new_invite_key()
    invitation.token_hash = hash_password(normalized)
    await db.flush()
    return invitation, display_key


async def accept_invitation(
    db: AsyncSession, *, tenant_slug: str, email: str, invite_key: str, password: str
) -> tuple[User, Tenant, TokenPair]:
    """Join a workspace with a shared invite key. Locates the pending invite by
    (workspace slug, email), verifies the key, creates the active user, and returns tokens
    for auto-login. Every failure raises the same generic error (no enumeration)."""
    email = email.lower()
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == tenant_slug.lower()))
    if tenant is None:
        raise InvalidInvitationError()

    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.tenant_id == tenant.id,
            Invitation.email == email,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    if (
        invitation is None
        or _is_expired(invitation.expires_at)
        or not verify_password(_normalize_key(invite_key), invitation.token_hash)
    ):
        raise InvalidInvitationError()

    # Guard against a race where the email got taken between invite and accept.
    existing_user = await db.scalar(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == email,
            User.deleted_at.is_(None),
        )
    )
    if existing_user is not None:
        raise ConflictError("A user with that email already exists in this tenant.")

    user = User(
        tenant_id=tenant.id,
        email=invitation.email,
        hashed_password=hash_password(password),
        role=invitation.role,
        is_active=True,
    )
    db.add(user)
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(UTC)
    await db.flush()

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


async def regenerate_token(
    db: AsyncSession, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID
) -> tuple[Invitation, str]:
    """Mint a fresh invite key for an existing PENDING invite and return the new display
    key. Lets a manager re-issue a key (e.g. to re-share over Slack) — the old key stops
    working since only the latest hash is stored. Tenant-scoped."""
    invitation = await db.get(Invitation, invitation_id)
    if (
        invitation is None
        or invitation.tenant_id != tenant_id
        or invitation.status != InvitationStatus.PENDING
    ):
        raise NotFoundError("Pending invitation not found.")
    display_key, normalized = _new_invite_key()
    invitation.token_hash = hash_password(normalized)
    await db.flush()
    return invitation, display_key


async def revoke(db: AsyncSession, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID) -> Invitation:
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.tenant_id != tenant_id:
        raise NotFoundError("Invitation not found.")
    invitation.status = InvitationStatus.REVOKED
    await db.flush()
    return invitation
