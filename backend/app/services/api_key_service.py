"""API key issuance + authentication for programmatic / MCP access.

A presented key looks like ``{prefix}.{secret}`` where ``prefix`` is stored in the clear
(for lookup + display) and ``secret`` is verified against an argon2 hash. Authentication
resolves the key to the same :class:`CurrentUser` shape the JWT path produces, so every
downstream ACL check is identical — a key can never exceed its principal's permissions.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.security import hash_password, verify_password
from app.models.api_key import ApiKey
from app.models.user import User


def _generate() -> tuple[str, str, str]:
    """Return ``(prefix, secret, full_key)`` for a fresh key."""
    prefix = f"{settings.API_KEY_PREFIX}_{secrets.token_hex(4)}"
    secret = secrets.token_urlsafe(32)
    return prefix, secret, f"{prefix}.{secret}"


async def issue(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """Create an API key acting as ``user_id``. Returns the row + the one-time full key."""
    prefix, secret, full_key = _generate()
    api_key = ApiKey(
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        prefix=prefix,
        key_hash=hash_password(secret),
        scopes=scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    return api_key, full_key


async def authenticate(db: AsyncSession, presented: str) -> CurrentUser | None:
    """Resolve a presented key to its principal, or ``None`` if invalid.

    Checks the secret hash, revocation, and expiry, and stamps ``last_used_at``.
    """
    prefix, _, secret = presented.partition(".")
    if not prefix or not secret:
        return None

    api_key = await db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if api_key is None or api_key.revoked_at is not None:
        return None
    if api_key.expires_at is not None and api_key.expires_at < datetime.now(UTC):
        return None
    if not verify_password(secret, api_key.key_hash):
        return None

    user = await db.get(User, api_key.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        return None

    api_key.last_used_at = datetime.now(UTC)
    await db.flush()
    return CurrentUser(id=user.id, tenant_id=user.tenant_id, role=user.role, email=user.email)
