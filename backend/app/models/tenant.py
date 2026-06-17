"""Tenant model — the root of multi-tenant isolation."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import GUID, JSONBType

if TYPE_CHECKING:
    from app.models.user import User


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Per-tenant policy (Phase 7): LLM routing overrides parsed by schemas.TenantSettings.
    # Nullable JSON; null ⇒ all defaults. Never holds secrets.
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, nullable=True)

    users: Mapped[list[User]] = relationship(back_populates="tenant")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Tenant id={self.id} slug={self.slug!r}>"
