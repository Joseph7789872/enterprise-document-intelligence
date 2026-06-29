"""Multi-agent query endpoints: ask, stream, fetch, approve/reject."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

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
from app.models.conversation import Conversation
from app.models.query import Query, QueryStatus
from app.models.user import UserRole
from app.observability.tracing import start_trace
from app.schemas.query import AnswerResponse, CitationOut, QueryRead, QueryRequest
from app.services import audit_service

router = APIRouter(prefix="/query", tags=["query"])

# How many prior turns of a thread to feed the planner for follow-up reference resolution.
_HISTORY_TURNS = 6


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


async def _validate_conversation(
    db: AsyncSession, current: CurrentUser, conversation_id: uuid.UUID
) -> Conversation:
    """Ensure a supplied thread belongs to the caller; 404 otherwise (no disclosure)."""
    convo = await db.get(Conversation, conversation_id)
    if convo is None or convo.tenant_id != current.tenant_id or convo.user_id != current.id:
        raise NotFoundError("Conversation not found.")
    return convo


async def _load_history(
    db: AsyncSession,
    current: CurrentUser,
    conversation_id: uuid.UUID | None,
    *,
    limit: int = _HISTORY_TURNS,
) -> list[tuple[str, str]]:
    """Prior answered turns of a thread as (question, answer) pairs, oldest→newest.

    User- and tenant-scoped, so a thread can never surface another user's turns. Returns
    [] for a one-shot ask (no conversation_id)."""
    if conversation_id is None:
        return []
    rows = await db.scalars(
        select(Query)
        .where(
            Query.tenant_id == current.tenant_id,
            Query.user_id == current.id,
            Query.conversation_id == conversation_id,
            Query.answer_encrypted.is_not(None),
        )
        .order_by(Query.created_at.desc())
        .limit(limit)
    )
    turns = [
        (decrypt_str(q.question_encrypted), decrypt_str(q.answer_encrypted))
        for q in rows.all()
        if q.answer_encrypted is not None
    ]
    turns.reverse()  # back to oldest→newest for the prompt
    return turns


async def _persist(
    db: AsyncSession,
    current: CurrentUser,
    *,
    question: str,
    state: AgentState,
    conversation_id: uuid.UUID | None = None,
) -> Query:
    status = state.get("status", QueryState.FAILED)
    answer = state.get("answer")
    query = Query(
        tenant_id=current.tenant_id,
        user_id=current.id,
        conversation_id=conversation_id,
        question_encrypted=encrypt_str(question),
        answer_encrypted=encrypt_str(answer) if answer else None,
        citations=_citations_json(state),
        confidence=_confidence(state),
        status=QueryStatus(status),
        encryption_key_version=settings.ENCRYPTION_KEY_VERSION,
        trace_id=get_trace_id(),
    )
    db.add(query)
    # Bump the thread's updated_at so most-recent-activity ordering is correct.
    if conversation_id is not None:
        convo = await db.get(Conversation, conversation_id)
        if convo is not None:
            convo.updated_at = datetime.now(UTC)
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

    if body.conversation_id is not None:
        await _validate_conversation(db, current, body.conversation_id)
    history = await _load_history(db, current, body.conversation_id)

    runner = _runner(db, current)
    graph = build_workflow(runner)
    initial: AgentState = {
        "question": body.question,
        "tenant_id": current.tenant_id,
        "user_id": current.id,
        "trace_id": get_trace_id(),
        "status": QueryState.PROCESSING,
        "conversation_id": body.conversation_id,
        "history": history,
    }
    try:
        with start_trace("query", tenant_id=current.tenant_id, user_id=current.id):
            state: AgentState = await graph.ainvoke(initial)
    except LLMRoutingError as exc:
        await _audit_route_denied(current, exc, ip=client_ip(request))
        raise
    query = await _persist(
        db, current, question=body.question, state=state, conversation_id=body.conversation_id
    )

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
        conversation_id=query.conversation_id,
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
        if body.conversation_id is not None:
            await _validate_conversation(db, current, body.conversation_id)
        history = await _load_history(db, current, body.conversation_id)
        state: AgentState = {
            "question": body.question,
            "tenant_id": current.tenant_id,
            "user_id": current.id,
            "trace_id": get_trace_id(),
            "conversation_id": body.conversation_id,
            "history": history,
        }
        try:
            with start_trace("query.stream", tenant_id=current.tenant_id, user_id=current.id):
                state.update(await runner.planner(state))
                state.update(await runner.retriever(state))
                state.update(await runner.verifier(state))

                if route_after_verify(state) == "human_review":
                    state.update(await runner.human_review(state))
                    query = await _persist(
                        db, current, question=body.question, state=state,
                        conversation_id=body.conversation_id,
                    )
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
                        "pending",
                        {
                            "query_id": str(query.id),
                            "status": query.status.value,
                            "conversation_id": str(query.conversation_id)
                            if query.conversation_id
                            else None,
                        },
                    )
                    return

                # Stream synthesis tokens.
                pieces: list[str] = []
                async for token in runner.synthesize_stream(state):
                    pieces.append(token)
                    yield _sse("token", {"text": token})
                state["answer"] = "".join(pieces)
                state.update(await runner.source_attributor(state))

                query = await _persist(
                    db, current, question=body.question, state=state,
                    conversation_id=body.conversation_id,
                )
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
                    {
                        "query_id": str(query.id),
                        "citations": _citations_json(state),
                        "confidence": _confidence(state),
                        "conversation_id": str(query.conversation_id)
                        if query.conversation_id
                        else None,
                    },
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
        conversation_id=query.conversation_id,
        saved=query.saved,
    )


@router.get("", response_model=list[QueryRead])
async def list_queries(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    saved_only: bool = False,
) -> list[QueryRead]:
    """The caller's own past queries (newest first) — the Q&A log. Tenant- and
    user-scoped; never exposes other users' or tenants' questions. Pass
    ``saved_only=true`` for the bookmarked-answers ("Saved") view."""
    limit = max(1, min(limit, 200))
    stmt = (
        select(Query)
        .where(Query.tenant_id == current.tenant_id, Query.user_id == current.id)
        .order_by(Query.created_at.desc())
        .limit(limit)
        .offset(max(0, offset))
    )
    if saved_only:
        stmt = stmt.where(Query.saved.is_(True))
    rows = await db.scalars(stmt)
    return [_to_query_read(q) for q in rows.all()]


@router.post("/{query_id}/save", response_model=QueryRead)
async def set_query_saved(
    query_id: uuid.UUID,
    saved: bool = True,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryRead:
    """Bookmark (or un-bookmark) one of the caller's own answers for the Saved view."""
    query = await db.get(Query, query_id)
    if (
        query is None
        or query.tenant_id != current.tenant_id
        or query.user_id != current.id
    ):
        raise NotFoundError("Query not found.")
    query.saved = saved
    await db.flush()
    return _to_query_read(query)


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
    current: CurrentUser = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AnswerResponse:
    """A manager approves a held query: synthesize the deferred answer and complete it.

    (The human-approval gate is off by default in the v1 sales product; this endpoint
    backs it when re-enabled. Only managers/admins may approve.) Retrieval runs
    unrestricted to reconstruct the true source set the asker would see.
    """
    query = await _load_pending(db, current, query_id)
    question = decrypt_str(query.question_encrypted)

    runner = WorkflowRunner(
        db,
        tenant_id=current.tenant_id,
        user_id=current.id,
        role=UserRole.OWNER,  # unrestricted retrieval (manager override)
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
            state.update(await runner.synthesizer(state))
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
    current: CurrentUser = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
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
