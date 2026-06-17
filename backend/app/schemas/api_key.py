"""API key schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_SCOPES = ["query", "search", "list", "get"]


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SCOPES))
    # The user the key acts as (defaults to the creating admin). Must be in-tenant.
    user_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    user_id: uuid.UUID
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    """Returned once at creation, including the plaintext key (never stored)."""

    key: str
