"""Evaluator service tests (deterministic FakeEvaluator + factory)."""

from __future__ import annotations

import pytest
from app.services.evaluation import (
    AggregateScores,
    EvalSample,
    FakeEvaluator,
    ItemScores,
    get_evaluator,
)

THRESHOLD = 0.7


@pytest.mark.asyncio
async def test_grounded_sample_scores_above_threshold() -> None:
    sample = EvalSample(
        item_id="hr-vacation-01",
        question="How many paid vacation days do employees accrue each year?",
        answer=(
            "According to the sources, Employees accrue twenty days of paid vacation "
            "leave each year. [1]"
        ),
        contexts=["Employees accrue twenty days of paid vacation leave each year."],
        reference="Employees accrue twenty days of paid vacation leave each year.",
    )
    [score] = await FakeEvaluator().evaluate([sample])
    assert score.faithfulness >= THRESHOLD
    assert score.context_precision >= THRESHOLD
    assert score.answer_relevancy >= THRESHOLD


@pytest.mark.asyncio
async def test_unsupported_answer_is_not_relevant() -> None:
    # The answer is grounded in the retrieved text but does not address the question.
    sample = EvalSample(
        item_id="unsupported-01",
        question="What is the company's parental leave policy?",
        answer=(
            "According to the sources, Every outbound pallet must be scanned and "
            "assigned a tracking number before it leaves the loading dock. [1]"
        ),
        contexts=["Every outbound pallet must be scanned and assigned a tracking number."],
        reference="The documents do not mention a parental leave policy.",
    )
    [score] = await FakeEvaluator().evaluate([sample])
    assert score.answer_relevancy < THRESHOLD


@pytest.mark.asyncio
async def test_empty_contexts_zero_faithfulness() -> None:
    sample = EvalSample(
        item_id="x",
        question="anything",
        answer="Some answer with no support.",
        contexts=[],
        reference="ref",
    )
    [score] = await FakeEvaluator().evaluate([sample])
    assert score.faithfulness == 0.0


def test_aggregate_means_and_pass() -> None:
    items = [
        ItemScores("a", 0.8, 0.9, 0.75),
        ItemScores("b", 0.9, 0.7, 0.85),
    ]
    agg = AggregateScores.from_items(items)
    assert agg.means["faithfulness"] == pytest.approx(0.85)
    assert agg.passed({"faithfulness": 0.7, "context_precision": 0.7, "answer_relevancy": 0.7})
    assert not agg.passed({"faithfulness": 0.9, "context_precision": 0.7, "answer_relevancy": 0.7})


def test_get_evaluator_is_fake_in_dev() -> None:
    # No ANTHROPIC key + ragas extra absent in the test env → fake.
    get_evaluator.cache_clear()
    assert isinstance(get_evaluator(), FakeEvaluator)
