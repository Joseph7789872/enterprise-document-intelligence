"""EvalResult model — the per-item scores within an :class:`EvalRun`.

One row per ground-truth question: the workflow's answer plus its RAGAS metric scores.
Eval content is synthetic test data and stored in the clear (the corpus is
non-confidential); rows are tenant-scoped to the eval tenant and cascade-deleted with
their run.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class EvalResult(Base, TimestampMixin, TenantMixin):
    __tablename__ = "eval_results"
    __table_args__ = (Index("ix_eval_results_eval_run_id", "eval_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )

    # Ground-truth item id from the dataset (e.g. "hr-vacation-01").
    item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)  # synthetic, plaintext
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)

    num_contexts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Verifier confidence from the workflow run — a secondary quality signal.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(nullable=False, default=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<EvalResult item={self.item_id} run={self.eval_run_id} passed={self.passed}>"
