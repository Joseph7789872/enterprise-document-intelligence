"""Ramp topic endpoints: AE-readable starter checklist + manager CRUD.

Any authenticated user (AE or manager) may list the curated ramp topics; only
managers (OWNER/ADMIN) may create, update, or delete them.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_current_user, get_db, require_role
from app.errors import NotFoundError
from app.models.audit_log import AuditAction
from app.models.ramp_topic import RampTopic
from app.models.user import UserRole
from app.schemas.curation import RampTopicCreate, RampTopicRead, RampTopicUpdate
from app.services import audit_service

router = APIRouter(prefix="/ramp", tags=["ramp"])

_manager = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get("/topics", response_model=list[RampTopicRead])
async def list_ramp_topics(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RampTopic]:
    """The tenant's curated ramp topics, ordered for the onboarding checklist."""
    rows = await db.scalars(
        select(RampTopic)
        .where(RampTopic.tenant_id == current.tenant_id)
        .order_by(RampTopic.sort_order, RampTopic.created_at)
    )
    return list(rows.all())


@router.post("/topics", response_model=RampTopicRead, status_code=status.HTTP_201_CREATED)
async def create_ramp_topic(
    body: RampTopicCreate,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> RampTopic:
    topic = RampTopic(
        tenant_id=current.tenant_id,
        title=body.title,
        suggested_question=body.suggested_question,
        sort_order=body.sort_order,
    )
    db.add(topic)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.RAMP_TOPIC_CREATED,
        actor_user_id=current.id,
        resource_type="ramp_topic",
        resource_id=str(topic.id),
        ip_address=client_ip(request),
        outcome="allow",
    )
    return topic


async def _load_topic(db: AsyncSession, current: CurrentUser, topic_id: uuid.UUID) -> RampTopic:
    topic = await db.get(RampTopic, topic_id)
    if topic is None or topic.tenant_id != current.tenant_id:
        raise NotFoundError("Ramp topic not found.")
    return topic


@router.patch("/topics/{topic_id}", response_model=RampTopicRead)
async def update_ramp_topic(
    topic_id: uuid.UUID,
    body: RampTopicUpdate,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> RampTopic:
    topic = await _load_topic(db, current, topic_id)
    if body.title is not None:
        topic.title = body.title
    if body.suggested_question is not None:
        topic.suggested_question = body.suggested_question
    if body.sort_order is not None:
        topic.sort_order = body.sort_order
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.RAMP_TOPIC_UPDATED,
        actor_user_id=current.id,
        resource_type="ramp_topic",
        resource_id=str(topic.id),
        ip_address=client_ip(request),
        outcome="allow",
    )
    return topic


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ramp_topic(
    topic_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    topic = await _load_topic(db, current, topic_id)
    await db.delete(topic)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.RAMP_TOPIC_DELETED,
        actor_user_id=current.id,
        resource_type="ramp_topic",
        resource_id=str(topic_id),
        ip_address=client_ip(request),
        outcome="allow",
    )
