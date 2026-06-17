"""ApiKey model — a per-tenant API key for the MCP server / programmatic access.

A key acts *as* a specific user (``user_id``); that user's role and ACL grants govern
everything the key can do — there is no privilege escalation through a key. Only the
short ``prefix`` is stored in the clear; the secret is argon2-hashed (``key_hash``) and
shown to the operator exactly once at creation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID, JSONBType


class ApiKey(Base, TimestampMixin, TenantMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Public, searchable prefix (e.g. "edip_ab12cd34"); the secret half is never stored.
    prefix: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Coarse scopes, e.g. ["query", "search", "list", "get"].
    scopes: Mapped[list] = mapped_column(JSONBType(), nullable=False)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ApiKey id={self.id} tenant={self.tenant_id} prefix={self.prefix}>"
