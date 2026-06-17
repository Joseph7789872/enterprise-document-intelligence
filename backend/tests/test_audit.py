"""Audit logging tests: events are written, scoped to tenant, and admin-gated."""

from __future__ import annotations

import uuid

import pytest
from app.models.audit_log import AuditAction, AuditLog
from app.services import audit_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_write_event_persists(db_session: AsyncSession) -> None:
    tenant_id = uuid.uuid4()
    await audit_service.write_event(
        db_session,
        tenant_id=tenant_id,
        action=AuditAction.LOGIN_SUCCEEDED,
        metadata={"k": "v"},
    )
    await db_session.commit()

    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.tenant_id == tenant_id))).all()
    assert len(rows) == 1
    assert rows[0].action == AuditAction.LOGIN_SUCCEEDED
    assert rows[0].event_metadata == {"k": "v"}


@pytest.mark.asyncio
async def test_register_and_login_emit_audit_events(client: AsyncClient, register_payload: dict, db_session: AsyncSession) -> None:
    await client.post("/auth/register", json=register_payload)
    await client.post(
        "/auth/login",
        json={
            "tenant_slug": register_payload["tenant_slug"],
            "email": register_payload["email"],
            "password": register_payload["password"],
        },
    )
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.TENANT_REGISTERED in actions
    assert AuditAction.USER_REGISTERED in actions
    assert AuditAction.LOGIN_SUCCEEDED in actions


@pytest.mark.asyncio
async def test_failed_login_is_audited(client: AsyncClient, register_payload: dict, db_session: AsyncSession) -> None:
    await client.post("/auth/register", json=register_payload)
    await client.post(
        "/auth/login",
        json={
            "tenant_slug": register_payload["tenant_slug"],
            "email": register_payload["email"],
            "password": "nope",
        },
    )
    failures = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.LOGIN_FAILED)
        )
    ).all()
    assert len(failures) == 1


@pytest.mark.asyncio
async def test_audit_logs_endpoint_is_tenant_scoped(client: AsyncClient) -> None:
    # Two tenants register independently.
    a = await client.post("/auth/register", json={
        "tenant_name": "Firm A", "tenant_slug": "firm-a",
        "email": "a@firma.com", "password": "password-aaaaaa",
    })
    await client.post("/auth/register", json={
        "tenant_name": "Firm B", "tenant_slug": "firm-b",
        "email": "b@firmb.com", "password": "password-bbbbbb",
    })

    token_a = a.json()["tokens"]["access_token"]
    logs = await client.get("/audit/logs", headers={"Authorization": f"Bearer {token_a}"})
    assert logs.status_code == 200
    data = logs.json()
    # Only Firm A's tenant id appears — no cross-tenant leakage.
    tenant_ids = {row["tenant_id"] for row in data}
    assert tenant_ids == {a.json()["tenant"]["id"]}


@pytest.mark.asyncio
async def test_audit_read_is_itself_audited(client: AsyncClient, register_payload: dict, db_session: AsyncSession) -> None:
    r = await client.post("/auth/register", json=register_payload)
    token = r.json()["tokens"]["access_token"]
    await client.get("/audit/logs", headers={"Authorization": f"Bearer {token}"})

    reads = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.AUDIT_READ)
        )
    ).all()
    assert len(reads) == 1


@pytest.mark.asyncio
async def test_member_cannot_read_audit_logs(client: AsyncClient, register_payload: dict, session_factory) -> None:
    """A non-admin/owner role is forbidden from the audit endpoint."""
    from app.models.user import User, UserRole

    r = await client.post("/auth/register", json=register_payload)
    tenant_id = uuid.UUID(r.json()["tenant"]["id"])

    # Create a MEMBER user directly and mint a token for them.
    from app.core.security import create_access_token
    from app.core.security import hash_password as _hash

    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id,
            email="member@acme.com",
            hashed_password=_hash("password-memberx"),
            role=UserRole.MEMBER,
            is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id

    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    resp = await client.get("/audit/logs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
