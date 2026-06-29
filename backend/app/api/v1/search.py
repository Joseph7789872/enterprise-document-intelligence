"""Hybrid search endpoint — tenant-isolated, re-ranked, audited."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_str
from app.core.deps import CurrentUser, client_ip, get_current_user, get_db
from app.models.audit_log import AuditAction
from app.models.document import Document
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services import audit_service, authz, retrieval
from app.services.authz import Permission
from app.services.embeddings import get_embedder
from app.services.reranker import get_reranker

router = APIRouter(tags=["search"])

_SNIPPET_CHARS = 400


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Hybrid retrieval: dense (vector) + BM25 candidates, deduped and cross-encoder
    re-ranked, scoped to the caller's tenant."""
    # Retrieval-time ACL: restrict to documents the caller may QUERY (None ⇒ unrestricted).
    allowed = await authz.accessible_document_ids(
        db,
        tenant_id=current.tenant_id,
        user_id=current.id,
        role=current.role,
        permission=Permission.QUERY,
    )
    # Optional ICP/segment scope, intersected with the ACL set. The None sentinel
    # (unrestricted) must be special-cased — `None & set` would raise.
    if body.segment_id is not None:
        seg_ids = await authz.segment_document_ids(
            db, tenant_id=current.tenant_id, segment_id=body.segment_id
        )
        allowed = seg_ids if allowed is None else (allowed & seg_ids)
    query_embedding = await get_embedder().embed_query(body.query)
    scored = await retrieval.hybrid_search(
        db,
        tenant_id=current.tenant_id,
        query=body.query,
        query_embedding=query_embedding,
        reranker=get_reranker(),
        final_k=body.top_k,
        allowed_document_ids=allowed,
    )

    # Resolve filenames for the involved documents (one query, tenant already scoped).
    results: list[SearchResult] = []
    filename_cache: dict = {}
    for sc in scored:
        chunk = sc.chunk
        if chunk.document_id not in filename_cache:
            doc = await db.get(Document, chunk.document_id)
            filename_cache[chunk.document_id] = doc.filename if doc else ""
        snippet = decrypt_str(chunk.content_encrypted)[:_SNIPPET_CHARS]
        results.append(
            SearchResult(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                score=sc.score,
                methods=list(sc.methods),
                snippet=snippet,
                filename=filename_cache[chunk.document_id],
            )
        )

    # Audit records exactly which documents/chunks were surfaced, plus method breakdown.
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.SEARCH_PERFORMED,
        actor_user_id=current.id,
        resource_type="search",
        metadata={
            "top_k": body.top_k,
            "returned": len(results),
            "bm25_enabled": settings.ENABLE_BM25,
            "reranker": settings.effective_reranker_provider,
            "document_ids": [str(r.document_id) for r in results],
            "chunk_ids": [str(r.chunk_id) for r in results],
        },
        ip_address=client_ip(request),
    )

    return SearchResponse(query=body.query, results=results)
