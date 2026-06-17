"""RAGAS evaluation providers.

``Evaluator`` is the interface the eval harness codes against. ``RagasEvaluator``
computes real **faithfulness**, **context_precision**, and **answer_relevancy** using
an LLM judge (Claude via ``langchain-anthropic``) and OpenAI embeddings — it needs the
optional ``[evals]`` extra. ``FakeEvaluator`` is a deterministic, network-free lexical
scorer so the default test suite and the always-on PR gate run fully offline.
``get_evaluator()`` picks one based on ``settings.effective_evals_provider``.

The three metrics, conceptually:
- **faithfulness** — is the answer grounded in (entailed by) the retrieved contexts?
- **context_precision** — are the retrieved contexts relevant to the question?
- **answer_relevancy** — does the answer actually address the question?

The deterministic scorer approximates each lexically; it is intentionally tuned so a
grounded answer scores above the gate thresholds and an unsupported one scores below,
making both gate outcomes testable without a key or network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import anyio

from app.core.config import settings

# The canonical metric names, in a stable order, used everywhere downstream.
METRIC_NAMES: tuple[str, ...] = ("faithfulness", "context_precision", "answer_relevancy")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Tokens too generic to signal grounding/relevance; ignored by the lexical scorer.
_STOPWORD_STR = (
    "the a an of to in on for and or is are was were be been do does did how what "
    "when where which who whom why this that these those it its as at by with from"
)
_STOPWORDS = frozenset(_STOPWORD_STR.split())


def _terms(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def _average_precision(q_terms: set[str], ctx_terms: list[set[str]]) -> float:
    """Average precision of the ranked contexts (relevant = shares a question term)."""
    if not ctx_terms or not q_terms:
        return 0.0
    relevant_seen = 0
    precision_sum = 0.0
    for k, ct in enumerate(ctx_terms, start=1):
        if q_terms & ct:
            relevant_seen += 1
            precision_sum += relevant_seen / k
    if relevant_seen == 0:
        return 0.0
    return precision_sum / relevant_seen


@dataclass(frozen=True)
class EvalSample:
    """One evaluation unit: a question, the workflow's answer, the retrieved contexts,
    and the ground-truth reference answer."""

    item_id: str
    question: str
    answer: str
    contexts: list[str]
    reference: str


@dataclass
class ItemScores:
    """Per-item metric scores in [0, 1]."""

    item_id: str
    faithfulness: float
    context_precision: float
    answer_relevancy: float

    def as_dict(self) -> dict[str, float]:
        return {
            "faithfulness": self.faithfulness,
            "context_precision": self.context_precision,
            "answer_relevancy": self.answer_relevancy,
        }


@dataclass
class AggregateScores:
    """Run-level mean of each metric, plus the per-item breakdown."""

    means: dict[str, float] = field(default_factory=dict)
    items: list[ItemScores] = field(default_factory=list)

    @classmethod
    def from_items(cls, items: list[ItemScores]) -> AggregateScores:
        if not items:
            return cls(means=dict.fromkeys(METRIC_NAMES, 0.0), items=[])
        means = {
            name: sum(getattr(i, name) for i in items) / len(items) for name in METRIC_NAMES
        }
        return cls(means=means, items=items)

    def passed(self, thresholds: dict[str, float]) -> bool:
        """A run passes only if every mean metric meets its threshold."""
        return all(self.means.get(name, 0.0) >= thresholds[name] for name in thresholds)


class Evaluator(Protocol):
    async def evaluate(self, samples: list[EvalSample]) -> list[ItemScores]:
        """Score each sample on the three RAGAS metrics."""
        ...


class FakeEvaluator:
    """Deterministic lexical scorer (no LLM, no network) for offline dev/test.

    Each metric is approximated with token-overlap heuristics over the (de-stopworded)
    question / answer / contexts:

    - faithfulness      = fraction of answer terms that appear in some context
    - context_precision = fraction of contexts that contain a question term
    - answer_relevancy  = recall of question terms by the answer + reference

    An answer with no supporting contexts (e.g. the unsupported ground-truth item)
    therefore scores near zero on faithfulness, driving the gate's failure path.
    """

    async def evaluate(self, samples: list[EvalSample]) -> list[ItemScores]:
        return [self._score(s) for s in samples]

    def _score(self, s: EvalSample) -> ItemScores:
        q_terms = _terms(s.question)
        a_terms = _terms(s.answer)
        ref_terms = _terms(s.reference)
        ctx_terms = [_terms(c) for c in s.contexts]
        all_ctx_terms: set[str] = set().union(*ctx_terms) if ctx_terms else set()

        # faithfulness: are the answer's claims supported by retrieved context?
        faithfulness = len(a_terms & all_ctx_terms) / len(a_terms) if a_terms else 0.0

        # context_precision: rank-aware, like RAGAS — reward putting relevant contexts
        # first. A context is "relevant" if it shares a question term. Average precision
        # over the ranked list, so a relevant top hit scores high even amid noise.
        context_precision = _average_precision(q_terms, ctx_terms)

        # answer_relevancy: does the answer cover the question (+ reference) intent?
        target = q_terms | ref_terms
        answer_relevancy = len(a_terms & target) / len(target) if target else 0.0

        return ItemScores(
            item_id=s.item_id,
            faithfulness=round(faithfulness, 4),
            context_precision=round(context_precision, 4),
            answer_relevancy=round(answer_relevancy, 4),
        )


class RagasEvaluator:
    """Real RAGAS metrics with a Claude judge + OpenAI embeddings.

    Heavy and key-dependent (the optional ``[evals]`` extra), so everything is imported
    lazily and the synchronous ``ragas.evaluate`` runs in a worker thread.
    """

    def __init__(self, judge_model: str, embedding_model: str, dimensions: int) -> None:
        self._judge_model = judge_model
        self._embedding_model = embedding_model
        self._dimensions = dimensions

    async def evaluate(self, samples: list[EvalSample]) -> list[ItemScores]:
        if not samples:
            return []
        return await anyio.to_thread.run_sync(self._evaluate_sync, samples)

    def _evaluate_sync(self, samples: list[EvalSample]) -> list[ItemScores]:
        from langchain_anthropic import ChatAnthropic
        from langchain_openai import OpenAIEmbeddings
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import answer_relevancy, context_precision, faithfulness

        dataset = EvaluationDataset.from_list(
            [
                {
                    "user_input": s.question,
                    "response": s.answer,
                    "retrieved_contexts": s.contexts,
                    "reference": s.reference,
                }
                for s in samples
            ]
        )
        judge = LangchainLLMWrapper(
            ChatAnthropic(model=self._judge_model, api_key=settings.ANTHROPIC_API_KEY)
        )
        embeddings = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(
                model=self._embedding_model,
                dimensions=self._dimensions,
                api_key=settings.OPENAI_API_KEY,
            )
        )
        result = evaluate(
            dataset=dataset,
            metrics=[faithfulness, context_precision, answer_relevancy],
            llm=judge,
            embeddings=embeddings,
        )
        # result.to_pandas() preserves sample order; map each row back to ItemScores.
        df = result.to_pandas()
        scores: list[ItemScores] = []
        for s, (_, row) in zip(samples, df.iterrows(), strict=True):
            scores.append(
                ItemScores(
                    item_id=s.item_id,
                    faithfulness=_clean(row.get("faithfulness")),
                    context_precision=_clean(row.get("context_precision")),
                    answer_relevancy=_clean(row.get("answer_relevancy")),
                )
            )
        return scores


def _clean(value: object) -> float:
    """Coerce a RAGAS score to a float, mapping NaN/None to 0.0 (conservative gate)."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else round(f, 4)  # f != f is the NaN check


@lru_cache
def get_evaluator() -> Evaluator:
    """Return the configured evaluator (cached per process)."""
    if settings.effective_evals_provider == "fake":
        return FakeEvaluator()
    return RagasEvaluator(
        judge_model=settings.EVAL_JUDGE_MODEL,
        embedding_model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )
