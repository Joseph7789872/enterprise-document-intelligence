"""Phase B: conversational chat — threads + saved/bookmarked answers.

Adds the ``conversations`` table and links ``queries`` to it (nullable ``conversation_id``
so existing one-shot queries are untouched), plus a ``saved`` flag for bookmarking. The
standalone FK on ``queries.conversation_id`` is added on PostgreSQL only (SQLite can't
ALTER-add a constraint; the ORM builds it from the model on the create_all dev/test path).

Revision ID: 0012_conversations
Revises: 0011_segments
Create Date: 2026-06-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID

# revision identifiers, used by Alembic.
revision: str = "0012_conversations"
down_revision: str | None = "0011_segments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_conversations_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_conversations_user_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.add_column("queries", sa.Column("conversation_id", GUID(), nullable=True))
    op.add_column(
        "queries", sa.Column("saved", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_index("ix_queries_conversation_id", "queries", ["conversation_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_queries_conversation_id_conversations", "queries", "conversations",
            ["conversation_id"], ["id"], ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint(
            "fk_queries_conversation_id_conversations", "queries", type_="foreignkey"
        )
    op.drop_index("ix_queries_conversation_id", table_name="queries")
    op.drop_column("queries", "saved")
    op.drop_column("queries", "conversation_id")
    op.drop_table("conversations")
