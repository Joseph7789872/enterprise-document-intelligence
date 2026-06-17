"""Read schemas for the evaluation dashboard endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.eval_run import EvalRunStatus


class EvalResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: str
    question: str
    answer: str | None
    faithfulness: float | None
    context_precision: float | None
    answer_relevancy: float | None
    num_contexts: int
    confidence: float | None
    passed: bool


class EvalRunSummary(BaseModel):
    """List-view row: the run-level outcome without per-item detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: EvalRunStatus
    passed: bool | None
    dataset_name: str
    dataset_size: int
    llm_provider: str
    evaluator_provider: str
    git_sha: str | None
    mean_faithfulness: float | None
    mean_context_precision: float | None
    mean_answer_relevancy: float | None
    thresholds: dict | None
    created_at: datetime
    finished_at: datetime | None


class EvalRunDetail(EvalRunSummary):
    """Detail view: the run summary plus its per-item results."""

    error_message: str | None
    results: list[EvalResultRead]
