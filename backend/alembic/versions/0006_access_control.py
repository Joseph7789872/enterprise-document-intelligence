"""Phase 5: access control (groups, memberships, ACLs) + audit hardening.

Creates groups / group_memberships / document_access_control, adds documents.matter_id
and audit_logs.outcome. On PostgreSQL, makes audit_logs append-only by revoking
UPDATE/DELETE and installing a trigger that raises on any mutation attempt.

Revision ID: 0006_access_control
Revises: 0005_eval_tables
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID, JSONBType

# revision identifiers, used by Alembic.
revision: str = "0006_access_control"
down_revision: str | None = "0005_eval_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_AUDIT_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION audit_logs_prevent_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only; % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "group_type",
            sa.Enum(
                "DEPARTMENT", "MATTER", "CLIENT", "TEAM", "CUSTOM",
                name="group_type", native_enum=False, length=20,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_groups_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_groups"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_groups_tenant_id_name"),
    )
    op.create_index("ix_groups_tenant_id", "groups", ["tenant_id"])

    op.create_table(
        "group_memberships",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("group_id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_group_memberships_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name="fk_group_memberships_group_id_groups", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_group_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_group_memberships"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_memberships_group_id_user_id"),
    )
    op.create_index("ix_group_memberships_tenant_id", "group_memberships", ["tenant_id"])
    op.create_index("ix_group_memberships_group_id", "group_memberships", ["group_id"])
    op.create_index("ix_group_memberships_user_id", "group_memberships", ["user_id"])

    op.create_table(
        "document_access_control",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("document_id", GUID(), nullable=False),
        sa.Column(
            "principal_type",
            sa.Enum("USER", "GROUP", name="principal_type", native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column("principal_id", GUID(), nullable=False),
        sa.Column("permissions", JSONBType(), nullable=False),
        sa.Column("granted_by_user_id", GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_document_access_control_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_document_access_control_document_id_documents", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_access_control"),
    )
    op.create_index("ix_document_access_control_tenant_id", "document_access_control", ["tenant_id"])
    op.create_index(
        "ix_document_access_control_tenant_id_document_id",
        "document_access_control", ["tenant_id", "document_id"],
    )
    op.create_index(
        "ix_document_access_control_principal",
        "document_access_control", ["principal_type", "principal_id"],
    )

    # documents.matter_id (optional matter/client filing).
    op.add_column("documents", sa.Column("matter_id", GUID(), nullable=True))
    op.create_index("ix_documents_matter_id", "documents", ["matter_id"])

    # audit_logs.outcome (allow/deny).
    op.add_column("audit_logs", sa.Column("outcome", sa.String(length=16), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Standalone ALTER ADD CONSTRAINT (unsupported on SQLite; the ORM builds this FK
        # from the model on the create_all dev/test path).
        op.create_foreign_key(
            "fk_documents_matter_id_groups", "documents", "groups",
            ["matter_id"], ["id"], ondelete="SET NULL",
        )
        # Make audit_logs append-only (defense in depth beyond the no-mutate service
        # path). SQLite dev/test rely on the application-level guarantee.
        op.execute(_AUDIT_TRIGGER_FN)
        op.execute(
            "CREATE TRIGGER audit_logs_append_only "
            "BEFORE UPDATE OR DELETE ON audit_logs "
            "FOR EACH ROW EXECUTE FUNCTION audit_logs_prevent_mutation();"
        )
        op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC;")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;")
        op.execute("DROP FUNCTION IF EXISTS audit_logs_prevent_mutation();")
        op.drop_constraint("fk_documents_matter_id_groups", "documents", type_="foreignkey")

    op.drop_column("audit_logs", "outcome")
    op.drop_index("ix_documents_matter_id", table_name="documents")
    op.drop_column("documents", "matter_id")

    op.drop_table("document_access_control")
    op.drop_table("group_memberships")
    op.drop_table("groups")
