"""BM25 keyword search tests (Python fallback path on SQLite)."""

from __future__ import annotations

import uuid

import pytest
from app.core.crypto import decrypt_str
from app.services import keyword_search


async def _upload_text(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text


@pytest.mark.asyncio
async def test_bm25_ranks_lexical_match_first(client, acme, db_session) -> None:
    await _upload_text(
        client, acme["headers"], "vacation.txt",
        "Employees receive twenty days of paid vacation leave each year. " * 6,
    )
    await _upload_text(
        client, acme["headers"], "security.txt",
        "All confidential client data must be encrypted at rest and in transit. " * 6,
    )

    hits = await keyword_search.search(
        db_session, tenant_id=uuid.UUID(acme["tenant_id"]), query="vacation leave", limit=10
    )
    assert hits
    top_chunk, top_score = hits[0]
    assert top_score > 0
    assert "vacation" in decrypt_str(top_chunk.content_encrypted).lower()


@pytest.mark.asyncio
async def test_bm25_is_tenant_isolated(client, acme, db_session) -> None:
    await _upload_text(
        client, acme["headers"], "secret.txt",
        "Acme internal merger strategy is confidential. " * 6,
    )
    # A different tenant id sees nothing.
    hits = await keyword_search.search(
        db_session, tenant_id=uuid.uuid4(), query="merger strategy", limit=10
    )
    assert hits == []


@pytest.mark.asyncio
async def test_bm25_empty_query_returns_empty(db_session) -> None:
    assert await keyword_search.search(
        db_session, tenant_id=uuid.uuid4(), query="   ", limit=10
    ) == []
