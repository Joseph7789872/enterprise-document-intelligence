"""Phase 3: queries table (multi-agent Q&A workflow).

Revision ID: 0004_queries
Revises: 0003_chunk_fts
Create Date: 2026-06-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID, JSONBType

# revision identifiers, used by Alembic.
revision: str = "0004_queries"
down_revision: str | None = "0003_chunk_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("question_encrypted", sa.Text(), nullable=False),
        sa.Column("answer_encrypted", sa.Text(), nullable=True),
        sa.Column("citations", JSONBType(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "PROCESSING", "COMPLETED", "PENDING_APPROVAL", "REJECTED", "FAILED",
                name="query_status", native_enum=False, length=20,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("encryption_key_version", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_queries_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_queries_user_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_queries"),
    )
    op.create_index("ix_queries_tenant_id", "queries", ["tenant_id"])
    op.create_index("ix_queries_tenant_id_status", "queries", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("queries")
