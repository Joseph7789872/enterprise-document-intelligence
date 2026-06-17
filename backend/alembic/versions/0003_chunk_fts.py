"""Phase 2: full-text search column on document_chunks.

Adds ``content_tsv`` (derived lexemes; full text stays in ``content_encrypted``) and,
on PostgreSQL, a GIN index for BM25/FTS via to_tsvector/plainto_tsquery.

Revision ID: 0003_chunk_fts
Revises: 0002_documents_and_chunks
Create Date: 2026-06-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import TSVector

# revision identifiers, used by Alembic.
revision: str = "0003_chunk_fts"
down_revision: str | None = "0002_documents_and_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("content_tsv", TSVector(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_document_chunks_content_tsv",
            "document_chunks",
            ["content_tsv"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index("ix_document_chunks_content_tsv", table_name="document_chunks")
    op.drop_column("document_chunks", "content_tsv")
