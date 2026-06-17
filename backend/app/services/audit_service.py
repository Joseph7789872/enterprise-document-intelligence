"""Audit logging service — the single sanctioned way to record audit events.

Every security-sensitive action across the platform must route through
:func:`write_event`. The function only ever *inserts*; there is deliberately no
update or delete path, preserving the append-only guarantee from the threat model.

The audit write is added to the caller's session but NOT committed here — it shares
the caller's transaction so the audit record and the action it describes commit
atomically (or roll back together). The exception is :func:`record_event_committed`,
used for events (like a failed login) that must persist even when the surrounding
request ultimately errors.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_trace_id
from app.db import session as db_session
from app.models.audit_log import AuditAction, AuditLog


def _build(
    *,
    tenant_id: uuid.UUID,
    action: AuditAction,
    actor_user_id: uuid.UUID | None,
    resource_type: str | None,
    resource_id: str | None,
    metadata: dict[str, Any] | None,
    ip_address: str | None,
    trace_id: str | None,
    outcome: str | None,
) -> AuditLog:
    return AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        event_metadata=metadata,
        ip_address=ip_address,
        trace_id=trace_id if trace_id is not None else get_trace_id(),
        outcome=outcome,
    )


async def write_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: AuditAction,
    actor_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    trace_id: str | None = None,
    outcome: str | None = None,
) -> AuditLog:
    """Append an audit event within the caller's transaction.

    Flushes (so the row gets an id) but does not commit — the caller's unit of work
    owns the commit, keeping the event atomic with the action it records.
    """
    entry = _build(
        tenant_id=tenant_id,
        action=action,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
        ip_address=ip_address,
        trace_id=trace_id,
        outcome=outcome,
    )
    session.add(entry)
    await session.flush()
    return entry


async def record_event_committed(
    *,
    tenant_id: uuid.UUID,
    action: AuditAction,
    actor_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    trace_id: str | None = None,
    outcome: str | None = None,
) -> None:
    """Persist an audit event in its own independent transaction.

    Use for events that must survive even if the surrounding request fails — e.g.
    a failed-login attempt, where authentication raises but the attempt must still
    be recorded for security monitoring.
    """
    # Resolve SessionLocal at call time (not import time) so test overrides apply.
    async with db_session.SessionLocal() as session:
        entry = _build(
            tenant_id=tenant_id,
            action=action,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            ip_address=ip_address,
            trace_id=trace_id,
            outcome=outcome,
        )
        session.add(entry)
        await session.commit()
