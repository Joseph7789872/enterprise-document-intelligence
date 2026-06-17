"""Phase 6: api_keys + data_subject_requests (compliance, observability, MCP).

Revision ID: 0007_compliance_mcp
Revises: 0006_access_control
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID, JSONBType

# revision identifiers, used by Alembic.
revision: str = "0007_compliance_mcp"
down_revision: str | None = "0006_access_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("prefix", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("scopes", JSONBType(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_api_keys_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_api_keys_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("prefix", name="uq_api_keys_prefix"),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])

    op.create_table(
        "data_subject_requests",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("subject_user_id", GUID(), nullable=True),
        sa.Column("subject_email", sa.String(length=320), nullable=False),
        sa.Column(
            "request_type",
            sa.Enum("ACCESS", "EXPORT", "ERASURE", name="dsr_type", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "RECEIVED", "IN_PROGRESS", "FULFILLED", "REJECTED",
                name="dsr_status", native_enum=False, length=20,
            ),
            nullable=False,
        ),
        sa.Column("requested_by_user_id", GUID(), nullable=False),
        sa.Column("result", JSONBType(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_data_subject_requests_tenant_id_tenants", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_subject_requests"),
    )
    op.create_index("ix_data_subject_requests_tenant_id", "data_subject_requests", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("data_subject_requests")
    op.drop_table("api_keys")
