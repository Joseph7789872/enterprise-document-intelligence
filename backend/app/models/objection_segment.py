"""ObjectionSegment — a many-to-many tag linking a saved objection to a segment.

Tenant-scoped join row (carries ``tenant_id`` for hard isolation). Both sides
cascade-delete: removing an objection or a segment removes its tags. Powers the AE
"objections for [segment]" filter in the chat's objection-lookup mode.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin
from app.db.types import GUID


class ObjectionSegment(Base, TenantMixin):
    __tablename__ = "objection_segments"
    __table_args__ = (
        UniqueConstraint(
            "objection_id", "segment_id", name="uq_objection_segments_objection_id_segment_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    objection_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("saved_objections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ObjectionSegment objection={self.objection_id} segment={self.segment_id}>"
