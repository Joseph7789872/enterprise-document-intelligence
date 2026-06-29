"""V1 sales repurpose: replace the legal document taxonomy with sales content metadata.

Renames ``documents.content_type`` (MIME) → ``mime_type``, adds the sales ``content_type``
category + rep/manager ``visibility`` columns, and drops the legal taxonomy
(``classification_level``, ``department``, ``matter_id``). Pre-1.0 with no production data,
so new not-null columns are backfilled from their defaults.

Revision ID: 0009_sales_content_metadata
Revises: 0008_tenant_settings
Create Date: 2026-06-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID

# revision identifiers, used by Alembic.
revision: str = "0009_sales_content_metadata"
down_revision: str | None = "0008_tenant_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SALES_CONTENT_TYPE = sa.Enum(
    "PRODUCT", "PRICING", "OBJECTIONS", "BATTLECARD", "CASE_STUDY", "SCRIPT",
    name="sales_content_type", native_enum=False, length=20,
)
_CONTENT_VISIBILITY = sa.Enum(
    "REP_VISIBLE", "MANAGER_ONLY",
    name="content_visibility", native_enum=False, length=20,
)


def upgrade() -> None:
    # MIME type column rename (frees the ``content_type`` name for the sales category).
    op.alter_column("documents", "content_type", new_column_name="mime_type")

    # Sales content category + rep/manager visibility. server_default backfills any rows.
    op.add_column(
        "documents",
        sa.Column("content_type", _SALES_CONTENT_TYPE, nullable=False, server_default="PRODUCT"),
    )
    op.add_column(
        "documents",
        sa.Column("visibility", _CONTENT_VISIBILITY, nullable=False, server_default="REP_VISIBLE"),
    )

    # Drop the legal taxonomy. matter_id carries a named FK + index (added in 0006).
    # The FK only exists on PostgreSQL (0006 creates it under the same guard; SQLite
    # can't ALTER-drop a constraint), so only drop it there.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("fk_documents_matter_id_groups", "documents", type_="foreignkey")
    op.drop_index("ix_documents_matter_id", table_name="documents")
    op.drop_column("documents", "matter_id")
    op.drop_column("documents", "department")
    op.drop_column("documents", "classification_level")


def downgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "classification_level",
            sa.Enum(
                "PUBLIC", "INTERNAL", "CONFIDENTIAL", "PRIVILEGED",
                name="classification_level", native_enum=False, length=20,
            ),
            nullable=False,
            server_default="INTERNAL",
        ),
    )
    op.add_column("documents", sa.Column("department", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("matter_id", GUID(), nullable=True))
    op.create_index("ix_documents_matter_id", "documents", ["matter_id"])
    # Standalone ALTER ADD CONSTRAINT is unsupported on SQLite; only restore the FK on
    # PostgreSQL (matching the 0006 guard that originally created it).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_documents_matter_id_groups", "documents", "groups",
            ["matter_id"], ["id"], ondelete="SET NULL",
        )

    op.drop_column("documents", "visibility")
    op.drop_column("documents", "content_type")
    op.alter_column("documents", "mime_type", new_column_name="content_type")
