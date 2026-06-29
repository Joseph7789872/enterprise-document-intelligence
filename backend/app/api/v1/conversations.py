"""Conversation (chat thread) endpoints: create, list, fetch-with-turns.

Threads are tenant- and user-scoped: a caller only ever sees their own conversations and
turns. Each turn is a ``Query`` row linked by ``conversation_id``; the Q/A is decrypted
into the response in memory only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_str
from app.core.deps import CurrentUser, get_current_user, get_db
from app.errors import NotFoundError
from app.models.conversation import Conversation
from app.models.query import Query
from app.schemas.conversation import ConversationCreate, ConversationDetail, ConversationRead
from app.schemas.query import CitationOut, QueryRead

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _load_owned(
    db: AsyncSession, current: CurrentUser, conversation_id: uuid.UUID
) -> Conversation:
    """Fetch a conversation owned by the caller, or 404 (no cross-user/tenant disclosure)."""
    convo = await db.get(Conversation, conversation_id)
    if convo is None or convo.tenant_id != current.tenant_id or convo.user_id != current.id:
        raise NotFoundError("Conversation not found.")
    return convo


def _turn_to_read(query: Query) -> QueryRead:
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


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    convo = Conversation(tenant_id=current.tenant_id, user_id=current.id, title=body.title)
    db.add(convo)
    await db.flush()
    return convo


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[Conversation]:
    """The caller's own threads, most-recently-updated first."""
    limit = max(1, min(limit, 200))
    rows = await db.scalars(
        select(Conversation)
        .where(
            Conversation.tenant_id == current.tenant_id,
            Conversation.user_id == current.id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(max(0, offset))
    )
    return list(rows.all())


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    """A thread and its turns (oldest first) for hydrating the transcript."""
    convo = await _load_owned(db, current, conversation_id)
    rows = await db.scalars(
        select(Query)
        .where(
            Query.tenant_id == current.tenant_id,
            Query.user_id == current.id,
            Query.conversation_id == convo.id,
        )
        .order_by(Query.created_at)
    )
    return ConversationDetail(
        id=convo.id,
        title=convo.title,
        created_at=convo.created_at,
        updated_at=convo.updated_at,
        turns=[_turn_to_read(q) for q in rows.all()],
    )
