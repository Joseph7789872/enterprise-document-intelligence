"""Authentication service: tenant/owner bootstrap, login, token refresh.

All credential-handling lives here so the API layer stays thin. Sensitive outcomes
(registration, successful/failed login, refresh) are recorded via the audit service.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.audit_log import AuditAction
from app.models.subscription import SubscriptionStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.auth import TokenPair
from app.services import audit_service, billing_service


class AuthError(Exception):
    """Base class for authentication/registration failures."""


class CredentialsError(AuthError):
    """Invalid email/password/tenant combination (intentionally vague)."""


class RegistrationConflict(AuthError):
    """Tenant slug already taken (or duplicate owner email)."""


def _issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value
        ),
        refresh_token=create_refresh_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role.value
        ),
    )


async def register_tenant_and_owner(
    session: AsyncSession,
    *,
    tenant_name: str,
    tenant_slug: str,
    email: str,
    password: str,
    ip_address: str | None = None,
) -> tuple[Tenant, User, TokenPair]:
    """Create a new tenant and its first owner user atomically."""
    existing = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if existing is not None:
        raise RegistrationConflict("That organization identifier is already in use.")

    tenant = Tenant(name=tenant_name, slug=tenant_slug, is_active=True)
    session.add(tenant)
    await session.flush()  # assign tenant.id

    owner = User(
        tenant_id=tenant.id,
        email=email.lower(),
        hashed_password=hash_password(password),
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(owner)
    await session.flush()  # assign owner.id

    await audit_service.write_event(
        session,
        tenant_id=tenant.id,
        action=AuditAction.TENANT_REGISTERED,
        actor_user_id=owner.id,
        resource_type="tenant",
        resource_id=str(tenant.id),
        metadata={"slug": tenant_slug},
        ip_address=ip_address,
    )
    await audit_service.write_event(
        session,
        tenant_id=tenant.id,
        action=AuditAction.USER_REGISTERED,
        actor_user_id=owner.id,
        resource_type="user",
        resource_id=str(owner.id),
        metadata={"role": owner.role.value},
        ip_address=ip_address,
    )

    # Start the tenant on the trial plan. Harmless when ENABLE_BILLING is off (the row
    # simply isn't enforced); needed so plan/usage are available the moment billing is on.
    sub = await billing_service.ensure_subscription(
        session, tenant_id=tenant.id, status=SubscriptionStatus.TRIALING
    )
    await audit_service.write_event(
        session,
        tenant_id=tenant.id,
        action=AuditAction.SUBSCRIPTION_CREATED,
        actor_user_id=owner.id,
        resource_type="subscription",
        resource_id=str(sub.id),
        metadata={"plan_key": sub.plan_key, "status": sub.status.value},
        ip_address=ip_address,
    )

    return tenant, owner, _issue_tokens(owner)


async def authenticate(
    session: AsyncSession,
    *,
    tenant_slug: str,
    email: str,
    password: str,
    ip_address: str | None = None,
) -> tuple[User, TokenPair]:
    """Verify credentials and issue tokens. Audits both success and failure."""
    tenant = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))

    user: User | None = None
    if tenant is not None:
        user = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == email.lower(),
                User.deleted_at.is_(None),
            )
        )

    # Constant-ish work + vague error to avoid user/tenant enumeration.
    password_ok = (
        user is not None
        and user.is_active
        and verify_password(password, user.hashed_password)
    )

    if not password_ok or tenant is None or user is None:
        # Record the failure out-of-band so it survives the raised error.
        await audit_service.record_event_committed(
            tenant_id=tenant.id if tenant is not None else _NULL_TENANT,
            action=AuditAction.LOGIN_FAILED,
            actor_user_id=user.id if user is not None else None,
            resource_type="user",
            metadata={"tenant_slug": tenant_slug, "email": email.lower()},
            ip_address=ip_address,
        )
        raise CredentialsError("Invalid credentials.")

    await audit_service.write_event(
        session,
        tenant_id=user.tenant_id,
        action=AuditAction.LOGIN_SUCCEEDED,
        actor_user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
    )
    return user, _issue_tokens(user)


async def refresh_tokens(
    session: AsyncSession,
    *,
    refresh_token: str,
    ip_address: str | None = None,
) -> TokenPair:
    """Validate a refresh token and mint a fresh token pair."""
    from app.core.security import TokenError

    try:
        payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
    except TokenError as exc:
        raise CredentialsError("Invalid refresh token.") from exc

    user = await session.scalar(
        select(User).where(
            User.id == uuid.UUID(payload.sub),
            User.tenant_id == uuid.UUID(payload.tenant_id),
            User.deleted_at.is_(None),
        )
    )
    if user is None or not user.is_active:
        raise CredentialsError("Invalid refresh token.")

    await audit_service.write_event(
        session,
        tenant_id=user.tenant_id,
        action=AuditAction.TOKEN_REFRESHED,
        actor_user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=ip_address,
    )
    return _issue_tokens(user)


# A placeholder tenant id used only to record login failures where no tenant matched.
# Keeps the audit row well-formed without leaking whether the tenant exists.
_NULL_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000000")
