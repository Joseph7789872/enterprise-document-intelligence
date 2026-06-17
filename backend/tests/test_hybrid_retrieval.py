"""Hybrid retrieval tests: dedup, top-k cap, provenance, tenant isolation."""

from __future__ import annotations

import uuid

import pytest
from app.services import retrieval
from app.services.embeddings import get_embedder
from app.services.reranker import FakeReranker


async def _upload_text(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text


@pytest.mark.asyncio
async def test_chunk_found_by_both_methods_is_deduped(client, acme, db_session) -> None:
    # A short doc → a single chunk. Querying its exact text makes BOTH the vector leg
    # (FakeEmbedder is deterministic by text) and BM25 surface the same chunk.
    sentence = "Remote work is permitted up to three days per week."
    await _upload_text(client, acme["headers"], "policy.txt", sentence)

    embedder = get_embedder()
    q_emb = await embedder.embed_query(sentence)
    results = await retrieval.hybrid_search(
        db_session,
        tenant_id=uuid.UUID(acme["tenant_id"]),
        query=sentence,
        query_embedding=q_emb,
        reranker=FakeReranker(),
    )
    assert results
    # No duplicate chunk ids — union+dedup worked.
    ids = [r.chunk.id for r in results]
    assert len(ids) == len(set(ids))
    # The matched chunk carries both methods as provenance.
    top = results[0]
    assert set(top.methods) == {"bm25", "vector"}


@pytest.mark.asyncio
async def test_results_capped_at_final_top_k(client, acme, db_session) -> None:
    # Upload enough distinct content to exceed FINAL_TOP_K (6).
    for i in range(10):
        await _upload_text(
            client, acme["headers"], f"doc{i}.txt",
            f"Document number {i} about topic alpha beta gamma delta number {i}.",
        )
    embedder = get_embedder()
    q_emb = await embedder.embed_query("topic alpha beta")
    results = await retrieval.hybrid_search(
        db_session,
        tenant_id=uuid.UUID(acme["tenant_id"]),
        query="topic alpha beta",
        query_embedding=q_emb,
        reranker=FakeReranker(),
        final_k=6,
    )
    assert len(results) <= 6
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_hybrid_is_tenant_isolated(client, acme, db_session) -> None:
    await _upload_text(client, acme["headers"], "secret.txt", "Confidential merger plan details.")
    embedder = get_embedder()
    q_emb = await embedder.embed_query("merger plan")
    results = await retrieval.hybrid_search(
        db_session,
        tenant_id=uuid.uuid4(),  # a tenant with no documents
        query="merger plan",
        query_embedding=q_emb,
        reranker=FakeReranker(),
    )
    assert results == []
