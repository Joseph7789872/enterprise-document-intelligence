"""FastAPI dependencies: DB session, current user, role gates, tenant context.

The current user is resolved entirely from a validated access token and a DB lookup
that re-checks tenant membership and active status — never from client-supplied ids.
This keeps tenant isolation enforced on every authenticated request.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenError, TokenType, decode_token
from app.db.session import get_session
from app.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.models.user import User, UserRole

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def client_ip(request: Request) -> str | None:
    """Best-effort client IP for audit records (honors a single proxy hop)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated principal, derived from the access token + DB."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    role: UserRole
    email: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except TokenError as exc:
        raise AuthenticationError("Invalid or expired token.") from exc

    user = await db.get(User, uuid.UUID(payload.sub))
    if (
        user is None
        or user.deleted_at is not None
        or not user.is_active
        or str(user.tenant_id) != payload.tenant_id
    ):
        raise AuthenticationError("User no longer valid.")

    return CurrentUser(
        id=user.id, tenant_id=user.tenant_id, role=user.role, email=user.email
    )


def require_role(
    *allowed: UserRole,
) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Dependency factory: allow only the given roles."""

    async def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise AuthorizationError("Insufficient role for this action.")
        return user

    return _guard


def require_feature(flag: str) -> Callable[[], Awaitable[None]]:
    """Dependency factory: 404 the route unless ``settings.<flag>`` is truthy.

    Used to fully hide enterprise surfaces in the v1 sales product. Reads the flag at
    request time (not import time), so the off-state is testable by monkeypatching settings
    while the route stays mounted in the shared test app.
    """

    async def _guard() -> None:
        if not getattr(settings, flag, False):
            raise NotFoundError("Not found.")

    return _guard
