#!/usr/bin/env python
"""Seed the evaluation corpus into the dedicated eval tenant (idempotent).

Run from anywhere; it adds the backend package to the path and uses the configured
``DATABASE_URL`` (SQLite offline, Postgres live). Safe to re-run.

    python evals/seed_eval_corpus.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the backend package importable when run as a top-level script.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.db.session import SessionLocal  # noqa: E402
from app.services.eval_seed import default_corpus_dir, ensure_eval_tenant, seed_corpus  # noqa: E402


async def main() -> None:
    async with SessionLocal() as db:
        tenant_id, owner_id = await ensure_eval_tenant(db)
        corpus_dir = default_corpus_dir()
        doc_ids = await seed_corpus(db, tenant_id=tenant_id, owner_user_id=owner_id)
    print(f"Eval tenant: {tenant_id}")
    print(f"Corpus dir:  {corpus_dir}")
    print(f"Seeded/verified {len(doc_ids)} document(s).")


if __name__ == "__main__":
    asyncio.run(main())
