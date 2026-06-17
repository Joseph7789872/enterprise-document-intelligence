"""DocumentChunk model — a single chunk of an ingested document.

Security: ``content_encrypted`` holds the chunk text envelope-encrypted (via
``encrypt_str``); plaintext chunk text is never persisted. The ``embedding`` is stored
in the clear because vector similarity must operate on it; ``tenant_id`` is denormalized
onto every chunk so retrieval can filter by tenant directly (defense in depth alongside
the documents FK).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base
from app.db.mixins import TenantMixin
from app.db.types import GUID, EmbeddingVector, JSONBType, TSVector

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentChunk(Base, TenantMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Envelope-encrypted chunk text (token from app.core.crypto.encrypt_str).
    content_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(
        EmbeddingVector(settings.EMBEDDING_DIMENSIONS), nullable=False
    )
    chunk_metadata: Mapped[dict | None] = mapped_column(JSONBType(), nullable=True)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Derived full-text search vector (lexemes only — never the plaintext). Populated
    # at ingestion on PostgreSQL; NULL on SQLite (keyword search falls back to Python).
    content_tsv: Mapped[str | None] = mapped_column(TSVector(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<DocumentChunk doc={self.document_id} idx={self.chunk_index}>"
