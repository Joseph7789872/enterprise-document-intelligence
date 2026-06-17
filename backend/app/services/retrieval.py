"""Tenant-scoped retrieval: dense (vector), sparse (BM25), and hybrid + re-ranking.

- ``vector_search`` — dense recall via pgvector ``<=>`` on PostgreSQL, Python cosine
  fallback elsewhere (dev/test).
- ``hybrid_search`` — union of dense + BM25 candidates, deduped by ``chunk_id``, then
  re-scored by a cross-encoder; returns the final top-k.

Tenant isolation is non-negotiable: ``tenant_id`` always comes from the caller's
authenticated context and is applied as a hard filter on every leg, never from client
input — cross-tenant chunks can't enter the candidate set.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_str
from app.models.document_chunk import DocumentChunk
from app.services import keyword_search
from app.services.reranker import Reranker


@dataclass(frozen=True)
class ScoredChunk:
    chunk: DocumentChunk
    score: float
    methods: tuple[str, ...] = field(default_factory=tuple)


# Sentinel semantics for ``allowed_document_ids`` throughout retrieval:
#   None      -> unrestricted (trusted caller: OWNER/ADMIN or internal eval path)
#   set(...)  -> only these document ids are visible
#   set()     -> deny-all (fail closed) — the caller has access to nothing
def _denies_all(allowed: set[uuid.UUID] | None) -> bool:
    return allowed is not None and len(allowed) == 0


# ── Dense (vector) ──────────────────────────────────────────────────────────────

async def vector_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    allowed_document_ids: set[uuid.UUID] | None = None,
) -> list[ScoredChunk]:
    if _denies_all(allowed_document_ids):
        return []
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        return await _vector_pg(session, tenant_id, query_embedding, top_k, allowed_document_ids)
    return await _vector_python(session, tenant_id, query_embedding, top_k, allowed_document_ids)


async def _vector_pg(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    allowed_document_ids: set[uuid.UUID] | None,
) -> list[ScoredChunk]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(DocumentChunk, distance.label("distance"))
        .where(DocumentChunk.tenant_id == tenant_id)
        .order_by(distance)
        .limit(top_k)
    )
    if allowed_document_ids is not None:
        stmt = stmt.where(DocumentChunk.document_id.in_(allowed_document_ids))
    rows = (await session.execute(stmt)).all()
    return [
        ScoredChunk(chunk=row[0], score=1.0 - float(row[1]), methods=("vector",))
        for row in rows
    ]


async def _vector_python(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    allowed_document_ids: set[uuid.UUID] | None,
) -> list[ScoredChunk]:
    stmt = select(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id)
    if allowed_document_ids is not None:
        stmt = stmt.where(DocumentChunk.document_id.in_(allowed_document_ids))
    chunks = list((await session.scalars(stmt)).all())
    scored = [
        ScoredChunk(
            chunk=c,
            score=_cosine_similarity(query_embedding, c.embedding),
            methods=("vector",),
        )
        for c in chunks
    ]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:top_k]


# ── Hybrid (vector ∪ BM25 → dedup → cross-encoder rerank) ───────────────────────

@dataclass
class _Candidate:
    chunk: DocumentChunk
    methods: set[str]
    vector_score: float | None = None
    bm25_score: float | None = None


async def hybrid_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    query: str,
    query_embedding: list[float],
    reranker: Reranker,
    vector_k: int | None = None,
    bm25_k: int | None = None,
    final_k: int | None = None,
    allowed_document_ids: set[uuid.UUID] | None = None,
) -> list[ScoredChunk]:
    vector_k = vector_k or settings.HYBRID_VECTOR_CANDIDATES
    bm25_k = bm25_k or settings.HYBRID_BM25_CANDIDATES
    final_k = final_k or settings.FINAL_TOP_K

    # Fail closed: a user with access to nothing retrieves nothing.
    if _denies_all(allowed_document_ids):
        return []

    # 1. Gather candidates from each method (both tenant-scoped + ACL-scoped).
    dense = await vector_search(
        session,
        tenant_id=tenant_id,
        query_embedding=query_embedding,
        top_k=vector_k,
        allowed_document_ids=allowed_document_ids,
    )
    sparse: list[tuple[DocumentChunk, float]] = []
    if settings.ENABLE_BM25:
        sparse = await keyword_search.search(
            session,
            tenant_id=tenant_id,
            query=query,
            limit=bm25_k,
            allowed_document_ids=allowed_document_ids,
        )

    # 2. Union + dedup by chunk id, tracking provenance + per-method scores.
    candidates: dict[uuid.UUID, _Candidate] = {}
    for sc in dense:
        candidates[sc.chunk.id] = _Candidate(
            chunk=sc.chunk, methods={"vector"}, vector_score=sc.score
        )
    for chunk, score in sparse:
        cand = candidates.get(chunk.id)
        if cand is None:
            candidates[chunk.id] = _Candidate(chunk=chunk, methods={"bm25"}, bm25_score=score)
        else:
            cand.methods.add("bm25")
            cand.bm25_score = score

    if not candidates:
        return []

    merged = list(candidates.values())

    # 3. Decrypt only the merged candidate set, then cross-encoder re-score.
    passages = [decrypt_str(c.chunk.content_encrypted) for c in merged]
    rerank_scores = await reranker.rerank(query, passages)

    # 4. Blend rerank with a normalized hybrid (fusion) score per RERANK_WEIGHT.
    w = settings.RERANK_WEIGHT
    fusion = _fusion_scores(dense, sparse) if w < 1.0 else None
    rr_norm = _minmax([rerank_scores[i] for i in range(len(merged))])

    results: list[ScoredChunk] = []
    for i, cand in enumerate(merged):
        if fusion is not None:
            final = w * rr_norm[i] + (1.0 - w) * fusion.get(cand.chunk.id, 0.0)
        else:
            final = float(rerank_scores[i])  # pure cross-encoder ordering
        results.append(
            ScoredChunk(chunk=cand.chunk, score=final, methods=tuple(sorted(cand.methods)))
        )

    results.sort(key=lambda s: s.score, reverse=True)
    return results[:final_k]


def _fusion_scores(
    dense: list[ScoredChunk], sparse: list[tuple[DocumentChunk, float]]
) -> dict[uuid.UUID, float]:
    """Reciprocal-rank fusion of the two ranked lists, min-max normalized."""
    rrf_k = 60
    scores: dict[uuid.UUID, float] = {}
    for rank, sc in enumerate(dense):
        scores[sc.chunk.id] = scores.get(sc.chunk.id, 0.0) + 1.0 / (rrf_k + rank)
    for rank, (chunk, _) in enumerate(sparse):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (rrf_k + rank)
    if not scores:
        return {}
    norm = _minmax(list(scores.values()))
    return dict(zip(scores.keys(), norm, strict=True))


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
