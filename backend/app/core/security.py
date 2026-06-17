"""Authentication primitives: password hashing and JWT encode/decode.

Passwords are hashed with Argon2id (memory-hard, the current OWASP-recommended
default). Tokens are signed JWTs carrying the tenant id and role so that every
downstream authorization check is tenant- and role-aware without an extra DB
lookup for the claims themselves.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError

from app.core.config import settings

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class TokenType(str, enum.Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(Exception):
    """Raised when a token is invalid, expired, or of the wrong type."""


class TokenPayload(BaseModel):
    """Validated JWT claims."""

    sub: str  # user id
    tenant_id: str
    role: str
    type: TokenType
    jti: str
    exp: int
    iat: int


# ── Passwords ──────────────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


# ── JWTs ─────────────────────────────────────────────────────────────────────────

def _create_token(
    *,
    user_id: uuid.UUID | str,
    tenant_id: uuid.UUID | str,
    role: str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": token_type.value,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(*, user_id: uuid.UUID | str, tenant_id: uuid.UUID | str, role: str) -> str:
    return _create_token(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(*, user_id: uuid.UUID | str, tenant_id: uuid.UUID | str, role: str) -> str:
    return _create_token(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, *, expected_type: TokenType | None = None) -> TokenPayload:
    """Decode and validate a JWT. Raises TokenError on any problem."""
    try:
        raw = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        payload = TokenPayload(**raw)
    except (JWTError, ValidationError) as exc:
        raise TokenError("Invalid or expired token.") from exc

    if expected_type is not None and payload.type != expected_type:
        raise TokenError(f"Expected a {expected_type.value} token.")
    return payload
