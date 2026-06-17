"""Reranker tests (FakeReranker + factory selection)."""

from __future__ import annotations

import pytest
from app.services.reranker import FakeReranker, get_reranker


@pytest.mark.asyncio
async def test_fake_reranker_scores_overlap() -> None:
    rr = FakeReranker()
    scores = await rr.rerank(
        "vacation policy days",
        [
            "Employees get twenty days of vacation each year.",  # high overlap
            "The kitchen is restocked on Mondays.",  # no overlap
        ],
    )
    assert scores[0] > scores[1]


@pytest.mark.asyncio
async def test_fake_reranker_empty_query() -> None:
    rr = FakeReranker()
    assert await rr.rerank("", ["anything"]) == [0.0]


@pytest.mark.asyncio
async def test_fake_reranker_empty_passages() -> None:
    rr = FakeReranker()
    assert await rr.rerank("query", []) == []


def test_factory_returns_fake_without_extra() -> None:
    # sentence-transformers is not installed in CI/dev → fake is used.
    assert isinstance(get_reranker(), FakeReranker)
