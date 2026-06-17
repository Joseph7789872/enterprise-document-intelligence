"""EvalRun model — one execution of the RAGAS evaluation gate over a dataset.

A run drives the real LangGraph workflow across a ground-truth dataset, scores each
answer on faithfulness / context_precision / answer_relevancy, and records the run-level
means against the configured thresholds. ``passed`` is the deploy gate signal.

The evaluation corpus is synthetic, non-confidential test data, so (unlike ``queries``)
eval content is stored in the clear. Runs are still tenant-scoped to a dedicated
``eval-harness`` tenant for isolation.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID, JSONBType


class EvalRunStatus(str, enum.Enum):
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class EvalRun(Base, TimestampMixin, TenantMixin):
    __tablename__ = "eval_runs"
    __table_args__ = (Index("ix_eval_runs_tenant_id_created_at", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # Nullable: CI-triggered runs have no user actor.
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluator_provider: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[EvalRunStatus] = mapped_column(
        Enum(EvalRunStatus, name="eval_run_status", native_enum=False, length=20),
        nullable=False,
        default=EvalRunStatus.RUNNING,
    )
    mean_faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The thresholds this run was gated against (so historical runs are interpretable).
    thresholds: Mapped[dict | None] = mapped_column(JSONBType(), nullable=True)
    passed: Mapped[bool | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<EvalRun id={self.id} status={self.status} passed={self.passed}>"
