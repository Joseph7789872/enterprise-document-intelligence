"""Eval gate tests: the deterministic threshold gate (always-on) + its failure path."""

from __future__ import annotations

import importlib.util
import os

import pytest
from app.core.config import settings
from app.models.eval_run import EvalRunStatus
from app.services.eval_harness import (
    GroundTruthDataset,
    GroundTruthItem,
    load_dataset,
    run_eval,
)
from app.services.eval_seed import ensure_eval_tenant, seed_corpus
from app.services.evaluation import FakeEvaluator


@pytest.mark.asyncio
async def test_ground_truth_dataset_passes_the_gate(client, db_session) -> None:
    """The committed dataset must clear every threshold (this is the deploy gate)."""
    tenant_id, owner_id = await ensure_eval_tenant(db_session)
    await seed_corpus(db_session, tenant_id=tenant_id, owner_user_id=owner_id)
    dataset = load_dataset(settings.EVAL_DATASET_PATH)

    run = await run_eval(
        db_session, tenant_id=tenant_id, user_id=owner_id,
        dataset=dataset, evaluator=FakeEvaluator(),
    )

    assert run.status == EvalRunStatus.PASSED
    assert run.passed is True
    thresholds = settings.eval_thresholds
    assert run.mean_faithfulness >= thresholds["faithfulness"]
    assert run.mean_context_precision >= thresholds["context_precision"]
    assert run.mean_answer_relevancy >= thresholds["answer_relevancy"]


@pytest.mark.asyncio
async def test_unanswerable_question_fails_the_gate(client, db_session) -> None:
    """An off-topic answer must fail relevancy → the gate fires (passed=False)."""
    tenant_id, owner_id = await ensure_eval_tenant(db_session)
    await seed_corpus(db_session, tenant_id=tenant_id, owner_user_id=owner_id)
    bad = GroundTruthDataset(
        name="failure_probe",
        items=[
            GroundTruthItem(
                id="unsupported-01",
                question="What is the company's parental leave policy?",
                ground_truth="The documents do not contain a parental leave policy.",
            )
        ],
    )

    run = await run_eval(
        db_session, tenant_id=tenant_id, user_id=owner_id,
        dataset=bad, evaluator=FakeEvaluator(),
    )

    assert run.passed is False
    assert run.status == EvalRunStatus.FAILED


@pytest.mark.ragas
@pytest.mark.skipif(
    importlib.util.find_spec("ragas") is None or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="real RAGAS needs the [evals] extra and ANTHROPIC_API_KEY",
)
@pytest.mark.asyncio
async def test_real_ragas_smoke(client, db_session) -> None:  # pragma: no cover - key-gated
    from app.services.evaluation import RagasEvaluator

    tenant_id, owner_id = await ensure_eval_tenant(db_session)
    await seed_corpus(db_session, tenant_id=tenant_id, owner_user_id=owner_id)
    dataset = load_dataset(settings.EVAL_DATASET_PATH)
    run = await run_eval(
        db_session, tenant_id=tenant_id, user_id=owner_id, dataset=dataset,
        evaluator=RagasEvaluator(
            judge_model=settings.EVAL_JUDGE_MODEL,
            embedding_model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        ),
    )
    assert run.mean_faithfulness is not None
