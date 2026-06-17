"""Evaluation harness — run the real workflow over a dataset, score it, persist.

``run_eval`` drives the actual :class:`WorkflowRunner` nodes (planner → retriever →
verifier → synthesizer → source_attributor) for each ground-truth question against the
seeded eval tenant, collects the answer + retrieved contexts, scores them with the
configured :class:`Evaluator`, and persists an :class:`EvalRun` + per-item
:class:`EvalResult` rows. ``EvalRun.passed`` is the deploy-gate signal.

The human-approval **halt** is intentionally bypassed here (an eval always needs an
answer to score), but the retrieval/synthesis code path is identical to production, so
the metrics reflect the real system. The verifier still runs so its confidence is
recorded per item as a secondary signal. All retrieval is tenant-scoped to the eval
tenant id passed in — the harness never crosses tenants.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import WorkflowRunner
from app.agents.state import AgentState
from app.core.config import settings
from app.models.audit_log import AuditAction
from app.models.eval_result import EvalResult
from app.models.eval_run import EvalRun, EvalRunStatus
from app.models.user import UserRole
from app.services import audit_service
from app.services.evaluation import METRIC_NAMES, AggregateScores, EvalSample, Evaluator

logger = logging.getLogger(__name__)


class GroundTruthItem(BaseModel):
    """One row of the ground-truth dataset."""

    id: str
    question: str
    ground_truth: str
    source_documents: list[str] = Field(default_factory=list)
    reference_contexts: list[str] = Field(default_factory=list)


class GroundTruthDataset(BaseModel):
    name: str = "ground_truth"
    items: list[GroundTruthItem]


def load_dataset(path: str | Path) -> GroundTruthDataset:
    """Load + validate the ground-truth dataset from JSON.

    Accepts either a bare list of items or an object with ``name``/``items``.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        name = Path(path).stem
        return GroundTruthDataset(name=name, items=[GroundTruthItem(**i) for i in raw])
    return GroundTruthDataset(**raw)


async def _answer_one(
    runner: WorkflowRunner, item: GroundTruthItem
) -> tuple[str, list[str], float | None]:
    """Run the workflow for one question, returning (answer, contexts, confidence).

    Bypasses the human-approval gate so every question yields a scorable answer.
    """
    state: AgentState = {
        "question": item.question,
        "tenant_id": runner.tenant_id,
        "user_id": runner.user_id,
        "trace_id": runner.trace_id,
    }
    state.update(await runner.planner(state))
    state.update(await runner.retriever(state))
    state.update(await runner.verifier(state))  # confidence signal; routing not applied
    state.update(await runner.synthesizer(state))
    state.update(await runner.source_attributor(state))

    contexts = [c.text for c in state.get("chunks", [])]
    verification = state.get("verification")
    confidence = verification.confidence if verification is not None else None
    return state.get("answer", "") or "", contexts, confidence


async def run_eval(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    dataset: GroundTruthDataset,
    evaluator: Evaluator,
    thresholds: dict[str, float] | None = None,
    git_sha: str | None = None,
    trace_id: str | None = None,
) -> EvalRun:
    """Execute one evaluation run end-to-end and persist its results.

    The caller owns the commit. On any unexpected failure the run is marked ERROR and
    the (un-raised) exception is recorded on the row.
    """
    thresholds = thresholds or settings.eval_thresholds

    run = EvalRun(
        tenant_id=tenant_id,
        triggered_by=user_id,
        git_sha=git_sha,
        dataset_name=dataset.name,
        dataset_size=len(dataset.items),
        llm_provider=settings.effective_llm_provider,
        evaluator_provider=settings.effective_evals_provider,
        status=EvalRunStatus.RUNNING,
        thresholds=thresholds,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=tenant_id,
        action=AuditAction.EVAL_RUN_STARTED,
        actor_user_id=user_id,
        resource_type="eval_run",
        resource_id=str(run.id),
        metadata={"dataset": dataset.name, "size": len(dataset.items)},
        trace_id=trace_id,
    )

    try:
        # The eval runs as the eval-tenant owner → unrestricted retrieval (no ACL filter).
        runner = WorkflowRunner(
            db, tenant_id=tenant_id, user_id=user_id, role=UserRole.OWNER, trace_id=trace_id
        )
        samples: list[EvalSample] = []
        confidences: dict[str, float | None] = {}
        context_counts: dict[str, int] = {}
        for item in dataset.items:
            answer, contexts, confidence = await _answer_one(runner, item)
            samples.append(
                EvalSample(
                    item_id=item.id,
                    question=item.question,
                    answer=answer,
                    contexts=contexts,
                    reference=item.ground_truth,
                )
            )
            confidences[item.id] = confidence
            context_counts[item.id] = len(contexts)

        item_scores = await evaluator.evaluate(samples)
        aggregate = AggregateScores.from_items(item_scores)

        scores_by_id = {s.item_id: s for s in item_scores}
        sample_by_id = {s.item_id: s for s in samples}
        for sid, score in scores_by_id.items():
            sample = sample_by_id[sid]
            item_passed = all(getattr(score, m) >= thresholds[m] for m in thresholds)
            db.add(
                EvalResult(
                    tenant_id=tenant_id,
                    eval_run_id=run.id,
                    item_id=sid,
                    question=sample.question,
                    answer=sample.answer,
                    faithfulness=score.faithfulness,
                    context_precision=score.context_precision,
                    answer_relevancy=score.answer_relevancy,
                    num_contexts=context_counts.get(sid, 0),
                    confidence=confidences.get(sid),
                    passed=item_passed,
                )
            )

        passed = aggregate.passed(thresholds)
        run.mean_faithfulness = aggregate.means.get("faithfulness")
        run.mean_context_precision = aggregate.means.get("context_precision")
        run.mean_answer_relevancy = aggregate.means.get("answer_relevancy")
        run.passed = passed
        run.status = EvalRunStatus.PASSED if passed else EvalRunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        await db.flush()

        await audit_service.write_event(
            db,
            tenant_id=tenant_id,
            action=AuditAction.EVAL_RUN_COMPLETED,
            actor_user_id=user_id,
            resource_type="eval_run",
            resource_id=str(run.id),
            metadata={
                "passed": passed,
                "means": {m: aggregate.means.get(m) for m in METRIC_NAMES},
                "thresholds": thresholds,
            },
            trace_id=trace_id,
        )
    except Exception as exc:  # noqa: BLE001 - record failure on the row, never crash the gate
        logger.exception("Eval run %s failed", run.id)
        run.status = EvalRunStatus.ERROR
        run.error_message = str(exc)[:2000]
        run.finished_at = datetime.now(UTC)
        await db.flush()

    return run
