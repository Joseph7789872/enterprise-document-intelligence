"""Phase 0 security foundation: tenants, users, audit_logs, compliance skeletons.

Revision ID: 0001_security_foundation
Revises:
Create Date: 2026-06-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID, JSONBType

# revision identifiers, used by Alembic.
revision: str = "0001_security_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # pgcrypto: available for any future DB-side crypto needs.
        # vector (pgvector): enabled now so later RAG phases need no infra change.
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── tenants ──────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("OWNER", "ADMIN", "MEMBER", "REVIEWER", name="user_role", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_users_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # ── audit_logs (append-only) ──────────────────────────────────────────────
    # No FK to tenants/users: audit history must outlive the entities it references.
    op.create_table(
        "audit_logs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("actor_user_id", GUID(), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "TENANT_REGISTERED", "USER_REGISTERED", "LOGIN_SUCCEEDED",
                "LOGIN_FAILED", "TOKEN_REFRESHED", "AUDIT_READ",
                name="audit_action", native_enum=False, length=50,
            ),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("event_metadata", JSONBType(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_tenant_id_created_at", "audit_logs", ["tenant_id", "created_at"])

    # ── data_retention_policies ───────────────────────────────────────────────
    op.create_table(
        "data_retention_policies",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_data_retention_policies_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_retention_policies"),
    )
    op.create_index("ix_data_retention_policies_tenant_id", "data_retention_policies", ["tenant_id"])

    # ── compliance_events ─────────────────────────────────────────────────────
    op.create_table(
        "compliance_events",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "DSR_REQUESTED", "DSR_FULFILLED", "RETENTION_PURGE", "POLICY_CHANGED",
                name="compliance_event_type", native_enum=False, length=50,
            ),
            nullable=False,
        ),
        sa.Column("details", JSONBType(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_compliance_events_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_compliance_events"),
    )
    op.create_index("ix_compliance_events_tenant_id", "compliance_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("compliance_events")
    op.drop_table("data_retention_policies")
    op.drop_table("audit_logs")
    op.drop_table("users")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
