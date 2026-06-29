"""Phase B: ICP / segments — managed list + many-to-many tags on content & objections.

Adds ``segments`` (a per-tenant managed list) plus ``document_segments`` and
``objection_segments`` join tables. All portable (GUID, no native enums, no PG-only ops),
so it runs identically on PostgreSQL and the SQLite dev/test path.

Revision ID: 0011_segments
Revises: 0010_ramp_and_objections
Create Date: 2026-06-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID

# revision identifiers, used by Alembic.
revision: str = "0011_segments"
down_revision: str | None = "0010_ramp_and_objections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _join_table(name: str, left: str, left_table: str) -> None:
    """A tenant-scoped many-to-many row linking ``left`` (e.g. document_id) to a segment."""
    op.create_table(
        name,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column(left, GUID(), nullable=False),
        sa.Column("segment_id", GUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=f"fk_{name}_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            [left], [f"{left_table}.id"], name=f"fk_{name}_{left}_{left_table}", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["segments.id"], name=f"fk_{name}_segment_id_segments", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{name}"),
        sa.UniqueConstraint(left, "segment_id", name=f"uq_{name}_{left}_segment_id"),
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index(f"ix_{name}_{left}", name, [left])
    op.create_index(f"ix_{name}_segment_id", name, ["segment_id"])


def upgrade() -> None:
    op.create_table(
        "segments",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_segments_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_segments"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_segments_tenant_id_name"),
    )
    op.create_index("ix_segments_tenant_id", "segments", ["tenant_id"])

    _join_table("document_segments", "document_id", "documents")
    _join_table("objection_segments", "objection_id", "saved_objections")


def downgrade() -> None:
    op.drop_table("objection_segments")
    op.drop_table("document_segments")
    op.drop_table("segments")
