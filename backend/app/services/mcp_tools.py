"""MCP tool implementations (transport-agnostic).

These are the four tools the MCP server exposes, written as plain async functions over a
DB session + an authenticated :class:`CurrentUser` principal. They reuse the exact same
ACL + retrieval + workflow code as the REST API, so an MCP client can never see anything
the principal couldn't — and every call is audited (``MCP_TOOL_CALLED``).

The thin stdio adapter in ``mcp_server/server.py`` wires these to the MCP SDK; keeping
the logic here makes it unit-testable without the SDK or a transport.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState, QueryState
from app.agents.workflow import build_workflow
from app.core.crypto import decrypt_str
from app.core.deps import CurrentUser
from app.core.logging import get_trace_id
from app.models.audit_log import AuditAction
from app.models.document import Document
from app.observability.tracing import start_trace
from app.services import audit_service, authz, retrieval
from app.services.authz import Permission
from app.services.embeddings import get_embedder
from app.services.reranker import get_reranker

_SNIPPET_CHARS = 400


async def _audit_tool(db: AsyncSession, principal: CurrentUser, tool: str, meta: dict) -> None:
    await audit_service.write_event(
        db,
        tenant_id=principal.tenant_id,
        action=AuditAction.MCP_TOOL_CALLED,
        actor_user_id=principal.id,
        resource_type="mcp",
        metadata={"tool": tool, **meta},
        outcome="allow",
    )


async def query_documents(
    db: AsyncSession, principal: CurrentUser, *, question: str
) -> dict[str, Any]:
    """Run the full multi-agent workflow and return a cited answer (ACL-enforced)."""
    from app.agents.nodes import WorkflowRunner

    runner = WorkflowRunner(
        db, tenant_id=principal.tenant_id, user_id=principal.id, role=principal.role,
        trace_id=get_trace_id(),
    )
    graph = build_workflow(runner)
    initial: AgentState = {
        "question": question,
        "tenant_id": principal.tenant_id,
        "user_id": principal.id,
        "trace_id": get_trace_id(),
        "status": QueryState.PROCESSING,
    }
    with start_trace("mcp.query_documents", tenant_id=principal.tenant_id, user_id=principal.id):
        state: AgentState = await graph.ainvoke(initial)

    citations = [c.model_dump(mode="json") for c in state.get("citations", [])]
    await _audit_tool(db, principal, "query_documents", {"citations": len(citations)})
    return {
        "status": state.get("status"),
        "requires_approval": bool(state.get("requires_approval")),
        "answer": state.get("answer"),
        "citations": citations,
    }


async def search_chunks(
    db: AsyncSession, principal: CurrentUser, *, query: str, top_k: int = 6
) -> dict[str, Any]:
    """Hybrid retrieval over the documents the principal may QUERY."""
    allowed = await authz.accessible_document_ids(
        db, tenant_id=principal.tenant_id, user_id=principal.id,
        role=principal.role, permission=Permission.QUERY,
    )
    embedding = await get_embedder().embed_query(query)
    scored = await retrieval.hybrid_search(
        db, tenant_id=principal.tenant_id, query=query, query_embedding=embedding,
        reranker=get_reranker(), final_k=top_k, allowed_document_ids=allowed,
    )
    filename_cache: dict[uuid.UUID, str] = {}
    results: list[dict[str, Any]] = []
    for sc in scored:
        chunk = sc.chunk
        if chunk.document_id not in filename_cache:
            doc = await db.get(Document, chunk.document_id)
            filename_cache[chunk.document_id] = doc.filename if doc else ""
        results.append(
            {
                "document_id": str(chunk.document_id),
                "chunk_id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "score": sc.score,
                "methods": list(sc.methods),
                "filename": filename_cache[chunk.document_id],
                "snippet": decrypt_str(chunk.content_encrypted)[:_SNIPPET_CHARS],
            }
        )
    await _audit_tool(db, principal, "search_chunks", {"returned": len(results)})
    return {"results": results}


async def list_documents(db: AsyncSession, principal: CurrentUser) -> dict[str, Any]:
    """List documents the principal may VIEW."""
    allowed = await authz.accessible_document_ids(
        db, tenant_id=principal.tenant_id, user_id=principal.id,
        role=principal.role, permission=Permission.VIEW,
    )
    stmt = (
        select(Document)
        .where(Document.tenant_id == principal.tenant_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    if allowed is not None:
        stmt = stmt.where(Document.id.in_(allowed))
    docs = list((await db.scalars(stmt)).all())
    await _audit_tool(db, principal, "list_documents", {"returned": len(docs)})
    return {
        "documents": [
            {
                "id": str(d.id),
                "filename": d.filename,
                "status": d.status.value,
                "classification_level": d.classification_level.value,
                "chunk_count": d.chunk_count,
            }
            for d in docs
        ]
    }


async def get_document(
    db: AsyncSession, principal: CurrentUser, *, document_id: uuid.UUID
) -> dict[str, Any]:
    """Fetch one document's metadata if the principal may VIEW it (else not found)."""
    document = await db.get(Document, document_id)
    if (
        document is None
        or document.tenant_id != principal.tenant_id
        or document.deleted_at is not None
    ):
        await _audit_tool(
            db, principal, "get_document", {"document_id": str(document_id), "found": False}
        )
        return {"error": "not_found"}

    allowed = await authz.can_access_document(
        db, tenant_id=principal.tenant_id, user_id=principal.id, role=principal.role,
        document_id=document.id, permission=Permission.VIEW,
    )
    await _audit_tool(
        db, principal, "get_document", {"document_id": str(document_id), "found": allowed}
    )
    if not allowed:
        return {"error": "not_found"}
    return {
        "id": str(document.id),
        "filename": document.filename,
        "content_type": document.content_type,
        "status": document.status.value,
        "classification_level": document.classification_level.value,
        "department": document.department,
        "page_count": document.page_count,
        "chunk_count": document.chunk_count,
        "created_at": document.created_at.isoformat(),
    }
