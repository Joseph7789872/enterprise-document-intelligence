"""Segment model — a manager-defined ICP / market segment for a tenant.

Segments (e.g. "Enterprise", "SMB", "Healthcare") are a per-tenant managed list. Content
(documents) and saved objections are tagged with zero-or-more segments so AEs can filter
"objections for [segment]" and, optionally, scope retrieval to a segment. Manager/admin
curated, tenant-scoped.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class Segment(Base, TimestampMixin, TenantMixin):
    __tablename__ = "segments"
    __table_args__ = (
        # Segment names are unique within a tenant (the managed list has no duplicates).
        UniqueConstraint("tenant_id", "name", name="uq_segments_tenant_id_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Lower sorts first; ties broken by created_at.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Segment id={self.id} tenant={self.tenant_id} name={self.name!r}>"
