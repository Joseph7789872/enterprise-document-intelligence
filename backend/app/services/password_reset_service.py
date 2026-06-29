"""Password reset — forgot-password → emailed link → set a new password (Phase D).

Same single-use, hash-at-rest token as invitations (``{token_id}.{secret}``). ``request_reset``
never reveals whether an account exists (no user enumeration): it always returns normally and
simply skips sending when there's no matching active user.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.errors import AppError
from app.models.audit_log import AuditAction
from app.models.password_reset_token import PasswordResetToken
from app.models.tenant import Tenant
from app.models.user import User
from app.services import audit_service
from app.services.email import templates
from app.services.email.sender import get_email_sender


class InvalidResetTokenError(AppError):
    """The reset token is unknown, already used, or expired."""

    status_code = 400
    message = "This password reset link is invalid or has expired."


def _new_token(token_id: uuid.UUID) -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    return f"{token_id.hex}.{secret}", secret


def _is_expired(expires_at: datetime) -> bool:
    """SQLite returns tz-naive datetimes — treat naive values as UTC before comparing."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < datetime.now(UTC)


async def request_reset(
    db: AsyncSession, *, tenant_slug: str, email: str, ip_address: str | None = None
) -> None:
    """Issue a reset token + email it, if the account exists. Always returns (no enumeration)."""
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if tenant is None:
        return
    user = await db.scalar(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == email.lower(),
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if user is None:
        return

    token_row = PasswordResetToken(
        tenant_id=tenant.id,
        user_id=user.id,
        token_hash="",  # set below once we have the id
        expires_at=datetime.now(UTC) + timedelta(hours=settings.RESET_TOKEN_TTL_HOURS),
    )
    db.add(token_row)
    await db.flush()  # assign id
    raw_token, secret = _new_token(token_row.id)
    token_row.token_hash = hash_password(secret)
    await db.flush()

    await get_email_sender().send(templates.reset_email(user.email, token=raw_token))
    await audit_service.write_event(
        db,
        tenant_id=tenant.id,
        action=AuditAction.PASSWORD_RESET_REQUESTED,
        actor_user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
    )


async def complete_reset(
    db: AsyncSession, *, raw_token: str, new_password: str, ip_address: str | None = None
) -> None:
    """Validate the token and set the user's new password. Single-use + TTL enforced."""
    token_id_hex, _, secret = raw_token.partition(".")
    if not token_id_hex or not secret:
        raise InvalidResetTokenError()
    try:
        token_id = uuid.UUID(hex=token_id_hex)
    except ValueError as exc:
        raise InvalidResetTokenError() from exc

    token_row = await db.get(PasswordResetToken, token_id)
    if (
        token_row is None
        or token_row.used_at is not None
        or _is_expired(token_row.expires_at)
        or not verify_password(secret, token_row.token_hash)
    ):
        raise InvalidResetTokenError()

    user = await db.get(User, token_row.user_id)
    if user is None or user.deleted_at is not None:
        raise InvalidResetTokenError()

    user.hashed_password = hash_password(new_password)
    token_row.used_at = datetime.now(UTC)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=token_row.tenant_id,
        action=AuditAction.PASSWORD_RESET_COMPLETED,
        actor_user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
    )
