"""Content model — an uploaded sales playbook/asset and its ingestion lifecycle.

The raw bytes live (envelope-encrypted) in object storage at ``storage_key``; this row
holds only metadata + status. ``content_type`` categorises the sales material and
``visibility`` controls whether reps (AEs) can see it or it is manager-only (e.g. floor
pricing / discounting guidance).
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


class SalesContentType(str, enum.Enum):
    """The kind of sales material a piece of content holds."""

    PRODUCT = "product"
    PRICING = "pricing"
    OBJECTIONS = "objections"
    BATTLECARD = "battlecard"
    CASE_STUDY = "case_study"
    SCRIPT = "script"  # discovery / demo scripts


class ContentVisibility(str, enum.Enum):
    """Who may see a piece of content. ``manager_only`` content is hidden from AEs and
    enforced at retrieval time (e.g. discounting / floor pricing)."""

    REP_VISIBLE = "rep_visible"
    MANAGER_ONLY = "manager_only"


# Retained for the model router's (currently un-wired) self-hosted routing capability and
# its unit tests; no document column references it in the v1 sales product.
class ClassificationLevel(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PRIVILEGED = "privileged"


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
    # MIME type of the uploaded bytes (e.g. "application/pdf"). Renamed from the former
    # ``content_type`` to free that name for the sales content category below.
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # SHA-256 of the *plaintext* bytes, for integrity checks and dedup.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Object-storage key for the envelope-encrypted bytes.
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Sales content category + rep/manager visibility (replaces the legal taxonomy).
    content_type: Mapped[SalesContentType] = mapped_column(
        Enum(SalesContentType, name="sales_content_type", native_enum=False, length=20),
        nullable=False,
        default=SalesContentType.PRODUCT,
    )
    visibility: Mapped[ContentVisibility] = mapped_column(
        Enum(ContentVisibility, name="content_visibility", native_enum=False, length=20),
        nullable=False,
        default=ContentVisibility.REP_VISIBLE,
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
