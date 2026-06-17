#!/usr/bin/env python
"""RAGAS evaluation gate.

Seeds the eval corpus, runs the real LangGraph workflow over the ground-truth dataset,
scores faithfulness / context_precision / answer_relevancy, persists an EvalRun, prints
a summary, and **exits non-zero if the run does not pass its thresholds** — so CI can
block a deploy on a quality regression.

    python evals/run_evals.py                  # provider from settings (fake offline)
    python evals/run_evals.py --provider ragas # real RAGAS (needs [evals] extra + key)
    python evals/run_evals.py --no-save        # don't persist to the database

Exit codes: 0 = passed, 1 = failed thresholds, 2 = run error.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make the backend package importable when run as a top-level script.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.eval_run import EvalRunStatus  # noqa: E402
from app.services.eval_harness import load_dataset, run_eval  # noqa: E402
from app.services.eval_seed import ensure_eval_tenant, seed_corpus  # noqa: E402
from app.services.evaluation import METRIC_NAMES, Evaluator, FakeEvaluator, RagasEvaluator  # noqa: E402


def _build_evaluator(provider: str | None) -> Evaluator:
    resolved = provider or settings.effective_evals_provider
    if resolved == "fake":
        return FakeEvaluator()
    return RagasEvaluator(
        judge_model=settings.EVAL_JUDGE_MODEL,
        embedding_model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )


def _print_summary(run, thresholds: dict[str, float]) -> None:  # type: ignore[no-untyped-def]
    print("\n" + "=" * 68)
    print(f"  Eval run {run.id}  [{run.status.value}]")
    print(f"  dataset={run.dataset_name} size={run.dataset_size} "
          f"llm={run.llm_provider} evaluator={run.evaluator_provider}")
    print("-" * 68)
    means = {
        "faithfulness": run.mean_faithfulness,
        "context_precision": run.mean_context_precision,
        "answer_relevancy": run.mean_answer_relevancy,
    }
    for metric in METRIC_NAMES:
        mean = means[metric]
        threshold = thresholds[metric]
        mark = "PASS" if (mean is not None and mean >= threshold) else "FAIL"
        shown = f"{mean:.3f}" if mean is not None else "  n/a"
        print(f"  {metric:<20} mean={shown}   threshold={threshold:.2f}   [{mark}]")
    print("-" * 68)
    print(f"  RESULT: {'PASSED' if run.passed else 'FAILED'}")
    if run.error_message:
        print(f"  ERROR: {run.error_message}")
    print("=" * 68 + "\n")


async def _run(args: argparse.Namespace) -> int:
    thresholds = settings.eval_thresholds
    dataset = load_dataset(args.dataset or settings.EVAL_DATASET_PATH)
    evaluator = _build_evaluator(args.provider)

    async with SessionLocal() as db:
        tenant_id, owner_id = await ensure_eval_tenant(db)
        await seed_corpus(db, tenant_id=tenant_id, owner_user_id=owner_id)
        run = await run_eval(
            db,
            tenant_id=tenant_id,
            user_id=owner_id,
            dataset=dataset,
            evaluator=evaluator,
            thresholds=thresholds,
            git_sha=args.git_sha,
        )
        if args.save:
            await db.commit()
        else:
            await db.rollback()

    _print_summary(run, thresholds)
    if run.status == EvalRunStatus.ERROR:
        return 2
    return 0 if run.passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAGAS evaluation gate.")
    parser.add_argument("--provider", choices=["ragas", "fake"], default=None,
                        help="Override the evaluator provider (default: from settings).")
    parser.add_argument("--dataset", default=None, help="Path to the ground-truth dataset.")
    parser.add_argument("--git-sha", default=None, help="Git SHA to record on the run.")
    parser.add_argument("--no-save", dest="save", action="store_false",
                        help="Do not persist the run to the database.")
    parser.set_defaults(save=True)
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
