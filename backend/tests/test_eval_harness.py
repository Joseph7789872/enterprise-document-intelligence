"""End-to-end eval harness tests (FakeLLM + FakeEvaluator over the real corpus)."""

from __future__ import annotations

import pytest
from app.core.config import settings
from app.models.eval_result import EvalResult
from app.models.eval_run import EvalRun, EvalRunStatus
from app.services.eval_harness import load_dataset, run_eval
from app.services.eval_seed import ensure_eval_tenant, seed_corpus
from app.services.evaluation import FakeEvaluator
from sqlalchemy import select


async def _seed_and_run(db) -> EvalRun:
    tenant_id, owner_id = await ensure_eval_tenant(db)
    await seed_corpus(db, tenant_id=tenant_id, owner_user_id=owner_id)
    dataset = load_dataset(settings.EVAL_DATASET_PATH)
    run = await run_eval(
        db,
        tenant_id=tenant_id,
        user_id=owner_id,
        dataset=dataset,
        evaluator=FakeEvaluator(),
    )
    await db.commit()
    return run


@pytest.mark.asyncio
async def test_harness_runs_and_persists(client, db_session) -> None:
    run = await _seed_and_run(db_session)

    assert run.status == EvalRunStatus.PASSED
    assert run.passed is True
    assert run.dataset_size > 0
    assert run.mean_faithfulness is not None
    assert run.evaluator_provider == "fake"

    results = (
        await db_session.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id))
    ).all()
    assert len(results) == run.dataset_size
    assert all(r.answer for r in results)


@pytest.mark.asyncio
async def test_harness_results_are_tenant_scoped(client, db_session) -> None:
    run = await _seed_and_run(db_session)
    results = (
        await db_session.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id))
    ).all()
    assert results
    assert all(r.tenant_id == run.tenant_id for r in results)
    # Every persisted run/result belongs to the dedicated eval tenant.
    runs = (await db_session.scalars(select(EvalRun))).all()
    assert {r.tenant_id for r in runs} == {run.tenant_id}
