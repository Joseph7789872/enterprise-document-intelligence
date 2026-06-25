"""V1 sales: manager-curated ramp topics + saved objection library.

Revision ID: 0010_ramp_and_objections
Revises: 0009_sales_content_metadata
Create Date: 2026-06-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID

# revision identifiers, used by Alembic.
revision: str = "0010_ramp_and_objections"
down_revision: str | None = "0009_sales_content_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _curated_table(name: str, *value_columns: sa.Column) -> None:
    op.create_table(
        name,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        *value_columns,
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=f"fk_{name}_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{name}"),
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])


def upgrade() -> None:
    _curated_table(
        "ramp_topics",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("suggested_question", sa.String(length=1000), nullable=False),
    )
    _curated_table(
        "saved_objections",
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.String(length=1000), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("saved_objections")
    op.drop_table("ramp_topics")
