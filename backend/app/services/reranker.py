"""Cross-encoder re-ranking.

The reranker scores each (query, passage) pair directly — far more precise than the
bi-encoder vector similarity used for first-stage recall. ``CrossEncoderReranker``
wraps ``sentence-transformers`` (the optional ``[reranker]`` extra) and runs the heavy,
synchronous model in a worker thread so it never blocks the event loop.
``FakeReranker`` is a deterministic, dependency-free stand-in for dev/test.
``get_reranker()`` selects one based on settings.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Protocol

import anyio

from app.core.config import settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Reranker(Protocol):
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        """Return a relevance score per passage (higher = more relevant)."""
        ...


class FakeReranker:
    """Deterministic lexical-overlap reranker (no model, no network).

    Scores by token-overlap recall of the query against each passage, so a passage
    that contains the query terms ranks above one that doesn't — enough for
    deterministic tests and key-/GPU-less development.
    """

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        q_terms = set(_TOKEN_RE.findall(query.lower()))
        if not q_terms:
            return [0.0] * len(passages)
        scores: list[float] = []
        for passage in passages:
            p_terms = set(_TOKEN_RE.findall(passage.lower()))
            scores.append(len(q_terms & p_terms) / len(q_terms))
        return scores


class CrossEncoderReranker:
    """sentence-transformers cross-encoder (e.g. ms-marco-MiniLM-L-6-v2)."""

    _BATCH = 32

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        # Model load is expensive; do it once per process (cached factory below).
        self._model = CrossEncoder(model_name)

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, p) for p in passages]
        # predict() is synchronous + CPU/GPU heavy → offload to a worker thread.
        scores = await anyio.to_thread.run_sync(
            lambda: self._model.predict(pairs, batch_size=self._BATCH)
        )
        return [float(s) for s in scores]


@lru_cache
def get_reranker() -> Reranker:
    """Return the configured reranker (cached per process)."""
    if settings.effective_reranker_provider == "fake":
        return FakeReranker()
    return CrossEncoderReranker(settings.RERANKER_MODEL)
