"""Saved objection model — a manager-curated entry in the objection library.

Each entry is a one-click prompt in the AE chat's objection-lookup quick mode (e.g.
label "Too expensive" → prompt "How do I handle 'your product is too expensive'?").
Manager/admin curated, tenant-scoped.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class SavedObjection(Base, TimestampMixin, TenantMixin):
    __tablename__ = "saved_objections"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Lower sorts first; ties broken by created_at.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<SavedObjection id={self.id} tenant={self.tenant_id} label={self.label!r}>"
