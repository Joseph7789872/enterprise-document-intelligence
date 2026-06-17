"""Phase 4: eval_runs + eval_results tables (RAGAS evaluation + CI gate).

Revision ID: 0005_eval_tables
Revises: 0004_queries
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.types import GUID, JSONBType

# revision identifiers, used by Alembic.
revision: str = "0005_eval_tables"
down_revision: str | None = "0004_queries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("triggered_by", GUID(), nullable=True),
        sa.Column("git_sha", sa.String(length=64), nullable=True),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("dataset_size", sa.Integer(), nullable=False),
        sa.Column("llm_provider", sa.String(length=32), nullable=False),
        sa.Column("evaluator_provider", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "RUNNING", "PASSED", "FAILED", "ERROR",
                name="eval_run_status", native_enum=False, length=20,
            ),
            nullable=False,
        ),
        sa.Column("mean_faithfulness", sa.Float(), nullable=True),
        sa.Column("mean_context_precision", sa.Float(), nullable=True),
        sa.Column("mean_answer_relevancy", sa.Float(), nullable=True),
        sa.Column("thresholds", JSONBType(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_eval_runs_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eval_runs"),
    )
    op.create_index("ix_eval_runs_tenant_id", "eval_runs", ["tenant_id"])
    op.create_index("ix_eval_runs_tenant_id_created_at", "eval_runs", ["tenant_id", "created_at"])

    op.create_table(
        "eval_results",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("eval_run_id", GUID(), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column("context_precision", sa.Float(), nullable=True),
        sa.Column("answer_relevancy", sa.Float(), nullable=True),
        sa.Column("num_contexts", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_eval_results_tenant_id_tenants", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["eval_run_id"], ["eval_runs.id"], name="fk_eval_results_eval_run_id_eval_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eval_results"),
    )
    op.create_index("ix_eval_results_tenant_id", "eval_results", ["tenant_id"])
    op.create_index("ix_eval_results_eval_run_id", "eval_results", ["eval_run_id"])


def downgrade() -> None:
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
