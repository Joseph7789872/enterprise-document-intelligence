"""DocumentSegment — a many-to-many tag linking a document to a segment.

Tenant-scoped join row (carries ``tenant_id`` for hard isolation, like every other
table). Both sides cascade-delete: removing a document or a segment removes its tags.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin
from app.db.types import GUID


class DocumentSegment(Base, TenantMixin):
    __tablename__ = "document_segments"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "segment_id", name="uq_document_segments_document_id_segment_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<DocumentSegment doc={self.document_id} segment={self.segment_id}>"
