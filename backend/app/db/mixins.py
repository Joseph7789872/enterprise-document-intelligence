"""Reusable ORM column mixins.

These encode cross-cutting concerns once so every model stays consistent:
- TimestampMixin: created/updated audit columns.
- SoftDeleteMixin: ``deleted_at`` for retention / soft-delete (never hard-delete
  records that may be subject to legal hold or retention policy).
- TenantMixin: ``tenant_id`` FK + index — the backbone of multi-tenant isolation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import GUID


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class TenantMixin:
    """Adds a tenant_id FK. Every tenant-scoped row carries this for isolation."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
