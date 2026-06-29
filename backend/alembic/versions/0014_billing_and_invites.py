"""Phase D: hosted-SaaS tables — subscriptions, invitations, password reset tokens.

All portable (GUID, native_enum=False, column-level FKs via CREATE TABLE — no standalone
ALTER), so they run identically on PostgreSQL and the SQLite dev/test path and are covered
by the upgrade/downgrade round-trip in tests/test_migrations.py.

Revision ID: 0014_billing_and_invites
Revises: 0013_connector_credentials
Create Date: 2026-06-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID

# revision identifiers, used by Alembic.
revision: str = "0014_billing_and_invites"
down_revision: str | None = "0013_connector_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUB_STATUS = sa.Enum(
    "TRIALING", "ACTIVE", "PAST_DUE", "CANCELED",
    name="subscription_status", native_enum=False, length=20,
)
_USER_ROLE = sa.Enum("OWNER", "ADMIN", "MEMBER", name="user_role", native_enum=False, length=20)
_INVITE_STATUS = sa.Enum(
    "PENDING", "ACCEPTED", "REVOKED", name="invitation_status", native_enum=False, length=20
)


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("plan_key", sa.String(length=50), nullable=False),
        sa.Column("status", _SUB_STATUS, nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_subscriptions_tenant_id_tenants", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.UniqueConstraint("tenant_id", name="uq_subscriptions_tenant_id"),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])

    op.create_table(
        "invitations",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", _USER_ROLE, nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", _INVITE_STATUS, nullable=False),
        sa.Column("invited_by_user_id", GUID(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_invitations_tenant_id_tenants", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"],
            name="fk_invitations_invited_by_user_id_users", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invitations"),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_password_reset_tokens_tenant_id_tenants", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_password_reset_tokens_user_id_users", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
    )
    op.create_index("ix_password_reset_tokens_tenant_id", "password_reset_tokens", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("invitations")
    op.drop_table("subscriptions")
