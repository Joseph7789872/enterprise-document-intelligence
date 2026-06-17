"""Phase 7: per-tenant settings (LLM routing policy).

Revision ID: 0008_tenant_settings
Revises: 0007_compliance_mcp
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import JSONBType

# revision identifiers, used by Alembic.
revision: str = "0008_tenant_settings"
down_revision: str | None = "0007_compliance_mcp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive, nullable JSON column — portable across PostgreSQL and SQLite.
    op.add_column("tenants", sa.Column("settings", JSONBType(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "settings")
