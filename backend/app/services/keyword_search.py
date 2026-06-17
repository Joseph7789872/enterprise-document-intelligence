"""BM25 / full-text keyword search over document chunks.

On PostgreSQL this uses the derived ``content_tsv`` column with
``plainto_tsquery`` + ``ts_rank_cd`` (GIN-indexed). On other backends (SQLite, used
by tests) there is no tsvector, so we decrypt the tenant's chunks and score them with
an in-process BM25 — correct but not scalable, strictly a dev/test path (parallel to
the dense fallback in ``retrieval``).

Tenant isolation: ``tenant_id`` always comes from the caller's authenticated context
and is applied as a hard filter.
"""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_str
from app.models.document_chunk import DocumentChunk

# BM25 parameters (Robertson/Spärck Jones defaults).
_K1 = 1.5
_B = 0.75
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]


async def search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    query: str,
    limit: int,
    allowed_document_ids: set[uuid.UUID] | None = None,
) -> list[tuple[DocumentChunk, float]]:
    if not query.strip():
        return []
    # Deny-all (fail closed): caller has access to no documents.
    if allowed_document_ids is not None and len(allowed_document_ids) == 0:
        return []
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        return await _search_pg(session, tenant_id, query, limit, allowed_document_ids)
    return await _search_python(session, tenant_id, query, limit, allowed_document_ids)


async def _search_pg(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    limit: int,
    allowed_document_ids: set[uuid.UUID] | None,
) -> list[tuple[DocumentChunk, float]]:
    tsquery = func.plainto_tsquery(settings.FTS_LANGUAGE, query)
    rank = func.ts_rank_cd(DocumentChunk.content_tsv, tsquery).label("rank")
    stmt = (
        select(DocumentChunk, rank)
        .where(
            DocumentChunk.tenant_id == tenant_id,
            DocumentChunk.content_tsv.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(limit)
    )
    if allowed_document_ids is not None:
        stmt = stmt.where(DocumentChunk.document_id.in_(allowed_document_ids))
    rows = (await session.execute(stmt)).all()
    return [(row[0], float(row[1])) for row in rows]


async def _search_python(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    limit: int,
    allowed_document_ids: set[uuid.UUID] | None,
) -> list[tuple[DocumentChunk, float]]:
    """In-process BM25 over the tenant's decrypted chunks (dev/test only)."""
    stmt = select(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id)
    if allowed_document_ids is not None:
        stmt = stmt.where(DocumentChunk.document_id.in_(allowed_document_ids))
    chunks = list((await session.scalars(stmt)).all())
    if not chunks:
        return []

    docs_tokens = [_tokenize(decrypt_str(c.content_encrypted)) for c in chunks]
    doc_lens = [len(toks) for toks in docs_tokens]
    avgdl = (sum(doc_lens) / len(doc_lens)) or 1.0
    n_docs = len(chunks)

    # Document frequency per term.
    df: Counter[str] = Counter()
    for toks in docs_tokens:
        for term in set(toks):
            df[term] += 1

    query_terms = set(_tokenize(query))
    scored: list[tuple[DocumentChunk, float]] = []
    for chunk, toks, dl in zip(chunks, docs_tokens, doc_lens, strict=True):
        tf = Counter(toks)
        score = 0.0
        for term in query_terms:
            if term not in tf:
                continue
            idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            denom = freq + _K1 * (1 - _B + _B * dl / avgdl)
            score += idf * (freq * (_K1 + 1)) / denom
        if score > 0.0:
            scored.append((chunk, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
