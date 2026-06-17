"""Chunking + embedding-provider tests."""

from __future__ import annotations

import pytest
from app.services import chunking
from app.services.embeddings import FakeEmbedder


def test_split_blank_returns_empty() -> None:
    assert chunking.split("   ") == []


def test_split_produces_chunks_with_token_counts() -> None:
    text = ("This is a sentence about secure document ingestion. " * 300)
    chunks = chunking.split(text)
    assert len(chunks) >= 2  # long text → multiple chunks
    assert all(c.token_count > 0 for c in chunks)
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    # Each chunk should respect (roughly) the configured size.
    assert all(c.token_count <= 512 + 50 for c in chunks)


@pytest.mark.asyncio
async def test_fake_embedder_is_deterministic_and_unit_norm() -> None:
    emb = FakeEmbedder(dim=3072)
    a1 = await emb.embed_query("hello world")
    a2 = await emb.embed_query("hello world")
    b = await emb.embed_query("different text")
    assert a1 == a2  # deterministic
    assert a1 != b
    assert len(a1) == 3072
    norm = sum(x * x for x in a1) ** 0.5
    assert abs(norm - 1.0) < 1e-6  # unit vector


@pytest.mark.asyncio
async def test_fake_embedder_batch_matches_single() -> None:
    emb = FakeEmbedder(dim=64)
    batch = await emb.embed_texts(["a", "b"])
    assert batch[0] == await emb.embed_query("a")
    assert len(batch) == 2
