"""Document model — an uploaded file and its ingestion lifecycle.

The raw bytes live (envelope-encrypted) in object storage at ``storage_key``; this
row holds only metadata + status. ``classification_level`` drives downstream handling
(e.g. routing privileged docs away from third-party embeddings in a later phase).
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk


class ClassificationLevel(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PRIVILEGED = "privileged"  # e.g. attorney-client privileged material


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base, TimestampMixin, SoftDeleteMixin, TenantMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_tenant_id_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # SHA-256 of the *plaintext* bytes, for integrity checks and dedup.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Object-storage key for the envelope-encrypted bytes.
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)

    classification_level: Mapped[ClassificationLevel] = mapped_column(
        Enum(ClassificationLevel, name="classification_level", native_enum=False, length=20),
        nullable=False,
        default=ClassificationLevel.INTERNAL,
    )
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional matter/client filing (FK groups). SET NULL so deleting a matter group
    # un-files its documents rather than deleting them.
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, name="ingestion_status", native_enum=False, length=20),
        nullable=False,
        default=IngestionStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Document id={self.id} tenant={self.tenant_id} status={self.status}>"
