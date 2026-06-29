"""Query model — a user question and its (encrypted) answer + status.

The question and answer are envelope-encrypted at rest (like document chunks); only
non-sensitive citation metadata (document/chunk ids, markers) is stored in the clear.
``status`` tracks the multi-agent workflow, including the PENDING_APPROVAL hold for
low-confidence answers awaiting human review.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID, JSONBType


class QueryStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    FAILED = "failed"


class Query(Base, TimestampMixin, TenantMixin):
    __tablename__ = "queries"
    __table_args__ = (
        Index("ix_queries_tenant_id_status", "tenant_id", "status"),
        Index("ix_queries_conversation_id", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # The chat thread this turn belongs to. Nullable so one-shot asks (and pre-Phase-B
    # rows) need no thread; CASCADE so deleting a conversation removes its turns.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True
    )
    # User-bookmarked answer (the History "Saved" filter).
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    question_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    answer_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Citation list (marker + document_id/chunk_id/filename) — ids only, not sensitive.
    citations: Mapped[list | None] = mapped_column(JSONBType(), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[QueryStatus] = mapped_column(
        Enum(QueryStatus, name="query_status", native_enum=False, length=20),
        nullable=False,
        default=QueryStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Query id={self.id} tenant={self.tenant_id} status={self.status}>"
