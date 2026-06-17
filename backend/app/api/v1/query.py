"""Multi-agent query endpoints: ask, stream, fetch, approve/reject."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import WorkflowRunner, route_after_verify
from app.agents.state import AgentState, QueryState
from app.agents.workflow import build_workflow
from app.core.config import settings
from app.core.crypto import decrypt_str, encrypt_str
from app.core.deps import CurrentUser, client_ip, get_current_user, get_db, require_role
from app.core.logging import get_trace_id
from app.errors import LLMRoutingError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.query import Query, QueryStatus
from app.models.user import UserRole
from app.observability.tracing import start_trace
from app.schemas.query import AnswerResponse, CitationOut, QueryRead, QueryRequest
from app.services import audit_service, authz
from app.services.authz import Permission

router = APIRouter(prefix="/query", tags=["query"])


def _runner(db: AsyncSession, current: CurrentUser) -> WorkflowRunner:
    return WorkflowRunner(
        db,
        tenant_id=current.tenant_id,
        user_id=current.id,
        role=current.role,
        trace_id=get_trace_id(),
    )


async def _audit_route_denied(
    current: CurrentUser, exc: LLMRoutingError, *, ip: str | None
) -> None:
    """Record a fail-closed routing denial in its own transaction (survives the request
    rollback that the 503 triggers), so the operator sees why the query was refused."""
    await audit_service.record_event_committed(
        tenant_id=current.tenant_id,
        action=AuditAction.LLM_ROUTE_DENIED,
        actor_user_id=current.id,
        resource_type="query",
        metadata={"reason": exc.message},
        ip_address=ip,
        trace_id=get_trace_id(),
        outcome="deny",
    )


def _citations_json(state: AgentState) -> list[dict]:
    return [c.model_dump(mode="json") for c in state.get("citations", [])]


def _confidence(state: AgentState) -> float | None:
    ver = state.get("verification")
    return ver.confidence if ver is not None else None


async def _persist(
    db: AsyncSession,
    current: CurrentUser,
    *,
    question: str,
    state: AgentState,
) -> Query:
    status = state.get("status", QueryState.FAILED)
    answer = state.get("answer")
    query = Query(
        tenant_id=current.tenant_id,
        user_id=current.id,
        question_encrypted=encrypt_str(question),
        answer_encrypted=encrypt_str(answer) if answer else None,
        citations=_citations_json(state),
        confidence=_confidence(state),
        status=QueryStatus(status),
        encryption_key_version=settings.ENCRYPTION_KEY_VERSION,
        trace_id=get_trace_id(),
    )
    db.add(query)
    await db.flush()
    return query


@router.post("", response_model=AnswerResponse)
async def ask(
    body: QueryRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnswerResponse:
    """Run the full multi-agent workflow and return a cited answer (or a pending hold)."""
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.QUERY_SUBMITTED,
        actor_user_id=current.id,
        resource_type="query",
        ip_address=client_ip(request),
    )

    runner = _runner(db, current)
    graph = build_workflow(runner)
    initial: AgentState = {
        "question": body.question,
        "tenant_id": current.tenant_id,
        "user_id": current.id,
        "trace_id": get_trace_id(),
        "status": QueryState.PROCESSING,
    }
    try:
        with start_trace("query", tenant_id=current.tenant_id, user_id=current.id):
            state: AgentState = await graph.ainvoke(initial)
    except LLMRoutingError as exc:
        await _audit_route_denied(current, exc, ip=client_ip(request))
        raise
    query = await _persist(db, current, question=body.question, state=state)

    requires_approval = bool(state.get("requires_approval"))
    action = AuditAction.QUERY_PENDING_APPROVAL if requires_approval else AuditAction.QUERY_ANSWERED
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=action,
        actor_user_id=current.id,
        resource_type="query",
        resource_id=str(query.id),
        metadata={
            "confidence": _confidence(state),
            "document_ids": [str(c["document_id"]) for c in _citations_json(state)],
            "chunk_ids": [str(c["chunk_id"]) for c in _citations_json(state)],
        },
        ip_address=client_ip(request),
    )

    return AnswerResponse(
        query_id=query.id,
        status=query.status,
        requires_approval=requires_approval,
        answer=state.get("answer"),
        citations=[CitationOut(**c) for c in _citations_json(state)],
        confidence=_confidence(state),
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
async def ask_stream(
    body: QueryRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the final answer token-by-token (SSE). Low-confidence → a pending event."""
    runner = _runner(db, current)

    async def generate() -> AsyncIterator[str]:
        await audit_service.write_event(
            db,
            tenant_id=current.tenant_id,
            action=AuditAction.QUERY_SUBMITTED,
            actor_user_id=current.id,
            resource_type="query",
            ip_address=client_ip(request),
        )
        state: AgentState = {
            "question": body.question,
            "tenant_id": current.tenant_id,
            "user_id": current.id,
            "trace_id": get_trace_id(),
        }
        try:
            with start_trace("query.stream", tenant_id=current.tenant_id, user_id=current.id):
                state.update(await runner.planner(state))
                state.update(await runner.retriever(state))
                state.update(await runner.verifier(state))

                if route_after_verify(state) == "human_review":
                    state.update(await runner.human_review(state))
                    query = await _persist(db, current, question=body.question, state=state)
                    await audit_service.write_event(
                        db,
                        tenant_id=current.tenant_id,
                        action=AuditAction.QUERY_PENDING_APPROVAL,
                        actor_user_id=current.id,
                        resource_type="query",
                        resource_id=str(query.id),
                    )
                    await db.commit()
                    yield _sse(
                        "pending", {"query_id": str(query.id), "status": query.status.value}
                    )
                    return

                # Stream synthesis tokens.
                pieces: list[str] = []
                async for token in runner.synthesize_stream(state):
                    pieces.append(token)
                    yield _sse("token", {"text": token})
                state["answer"] = "".join(pieces)
                state.update(await runner.source_attributor(state))

                query = await _persist(db, current, question=body.question, state=state)
                await audit_service.write_event(
                    db,
                    tenant_id=current.tenant_id,
                    action=AuditAction.QUERY_ANSWERED,
                    actor_user_id=current.id,
                    resource_type="query",
                    resource_id=str(query.id),
                    metadata={"confidence": _confidence(state)},
                )
                await db.commit()
                yield _sse(
                    "done",
                    {"query_id": str(query.id), "citations": _citations_json(state)},
                )
        except LLMRoutingError as exc:
            # Fail-closed: a sensitive route needed a self-hosted model that isn't
            # configured. Audit it (own transaction) and emit a terminal error event.
            await _audit_route_denied(current, exc, ip=client_ip(request))
            yield _sse("error", {"detail": exc.message, "status": exc.status_code})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _to_query_read(query: Query) -> QueryRead:
    """Decrypt a stored Query into the API read model (question/answer in the clear only
    in this in-memory response)."""
    return QueryRead(
        id=query.id,
        status=query.status,
        question=decrypt_str(query.question_encrypted),
        answer=decrypt_str(query.answer_encrypted) if query.answer_encrypted else None,
        citations=[CitationOut(**c) for c in (query.citations or [])],
        confidence=query.confidence,
        created_at=query.created_at,
    )


@router.get("", response_model=list[QueryRead])
async def list_queries(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[QueryRead]:
    """The caller's own past queries (newest first) — the Q&A log. Tenant- and
    user-scoped; never exposes other users' or tenants' questions."""
    limit = max(1, min(limit, 200))
    rows = await db.scalars(
        select(Query)
        .where(Query.tenant_id == current.tenant_id, Query.user_id == current.id)
        .order_by(Query.created_at.desc())
        .limit(limit)
        .offset(max(0, offset))
    )
    return [_to_query_read(q) for q in rows.all()]


@router.get("/{query_id}", response_model=QueryRead)
async def get_query(
    query_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryRead:
    query = await db.get(Query, query_id)
    if query is None or query.tenant_id != current.tenant_id:
        raise NotFoundError("Query not found.")
    return QueryRead(
        id=query.id,
        status=query.status,
        question=decrypt_str(query.question_encrypted),
        answer=decrypt_str(query.answer_encrypted) if query.answer_encrypted else None,
        citations=[CitationOut(**c) for c in (query.citations or [])],
        confidence=query.confidence,
        created_at=query.created_at,
    )


async def _load_pending(db: AsyncSession, current: CurrentUser, query_id: uuid.UUID) -> Query:
    query = await db.get(Query, query_id)
    if query is None or query.tenant_id != current.tenant_id:
        raise NotFoundError("Query not found.")
    return query


@router.post("/{query_id}/approve", response_model=AnswerResponse)
async def approve_query(
    query_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(
        require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.REVIEWER)
    ),
    db: AsyncSession = Depends(get_db),
) -> AnswerResponse:
    """Reviewer approves a held query: synthesize an answer and complete it.

    A held query has no citations yet (synthesis was deferred), so reviewer scoping is
    enforced against the *retrieved source documents*: a non-privileged REVIEWER may
    approve only if they hold ``REVIEW`` on every document feeding the answer. Retrieval
    runs unrestricted here (to reconstruct the true source set the asker would see),
    then the per-document REVIEW gate is applied before synthesis.
    """
    query = await _load_pending(db, current, query_id)
    question = decrypt_str(query.question_encrypted)

    runner = WorkflowRunner(
        db,
        tenant_id=current.tenant_id,
        user_id=current.id,
        role=UserRole.OWNER,  # unrestricted retrieval; REVIEW gate applied below
        trace_id=get_trace_id(),
    )
    state: AgentState = {
        "question": question,
        "tenant_id": current.tenant_id,
        "user_id": current.id,
        "trace_id": get_trace_id(),
    }
    try:
        with start_trace("query.approve", tenant_id=current.tenant_id, user_id=current.id):
            state.update(await runner.planner(state))
            state.update(await runner.retriever(state))

            # Per-document REVIEW gate for non-privileged reviewers.
            if not authz.is_privileged(current.role):
                for document_id in {c.document_id for c in state.get("chunks", [])}:
                    await authz.assert_can(
                        db,
                        tenant_id=current.tenant_id,
                        user_id=current.id,
                        role=current.role,
                        document_id=document_id,
                        permission=Permission.REVIEW,
                        ip_address=client_ip(request),
                    )

            state.update(await runner.synthesizer(state))  # human override — bypass the gate
            state.update(await runner.source_attributor(state))
    except LLMRoutingError as exc:
        await _audit_route_denied(current, exc, ip=client_ip(request))
        raise

    query.answer_encrypted = encrypt_str(state["answer"])
    query.citations = _citations_json(state)
    query.status = QueryStatus.COMPLETED
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.QUERY_APPROVED,
        actor_user_id=current.id,
        resource_type="query",
        resource_id=str(query.id),
        ip_address=client_ip(request),
    )
    return AnswerResponse(
        query_id=query.id,
        status=query.status,
        requires_approval=False,
        answer=state.get("answer"),
        citations=[CitationOut(**c) for c in _citations_json(state)],
        confidence=query.confidence,
    )


@router.post("/{query_id}/reject", response_model=QueryRead)
async def reject_query(
    query_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(
        require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.REVIEWER)
    ),
    db: AsyncSession = Depends(get_db),
) -> QueryRead:
    query = await _load_pending(db, current, query_id)
    query.status = QueryStatus.REJECTED
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.QUERY_REJECTED,
        actor_user_id=current.id,
        resource_type="query",
        resource_id=str(query.id),
        ip_address=client_ip(request),
    )
    return QueryRead(
        id=query.id,
        status=query.status,
        question=decrypt_str(query.question_encrypted),
        answer=None,
        citations=[],
        confidence=query.confidence,
        created_at=query.created_at,
    )
