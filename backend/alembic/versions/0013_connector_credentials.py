"""Phase C: per-tenant encrypted connector credentials (Notion + future providers).

One row per (tenant, provider) holding an encrypted token. Portable (GUID, native_enum=
False, column-level tenant FK via CREATE TABLE — no standalone ALTER), so it runs
identically on PostgreSQL and the SQLite dev/test path.

Revision ID: 0013_connector_credentials
Revises: 0012_conversations
Create Date: 2026-06-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID

# revision identifiers, used by Alembic.
revision: str = "0013_connector_credentials"
down_revision: str | None = "0012_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVIDER = sa.Enum("NOTION", name="connector_provider", native_enum=False, length=32)


def upgrade() -> None:
    op.create_table(
        "connector_credentials",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("provider", _PROVIDER, nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_connector_credentials_tenant_id_tenants", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_connector_credentials"),
        sa.UniqueConstraint(
            "tenant_id", "provider", name="uq_connector_credentials_tenant_id_provider"
        ),
    )
    op.create_index("ix_connector_credentials_tenant_id", "connector_credentials", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("connector_credentials")
