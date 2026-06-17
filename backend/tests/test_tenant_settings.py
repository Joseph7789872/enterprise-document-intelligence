"""Tenant settings admin API tests (Phase 7) — role-gated, audited, honored by routing."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User, UserRole
from sqlalchemy import select


async def _member(db, session_factory, tenant_id: uuid.UUID) -> dict:
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="member@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id
    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_defaults_when_unset(client, acme) -> None:
    r = await client.get("/admin/tenant/settings", headers=acme["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["require_self_hosted_llm"] is False
    assert body["sensitive_classification"] == "confidential"


@pytest.mark.asyncio
async def test_put_get_round_trip_and_audit(client, acme, db_session) -> None:
    put = await client.put(
        "/admin/tenant/settings",
        json={"require_self_hosted_llm": True, "sensitive_classification": "privileged"},
        headers=acme["headers"],
    )
    assert put.status_code == 200, put.text
    assert put.json()["require_self_hosted_llm"] is True

    got = await client.get("/admin/tenant/settings", headers=acme["headers"])
    assert got.json()["sensitive_classification"] == "privileged"

    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.TENANT_SETTINGS_UPDATED in actions


@pytest.mark.asyncio
async def test_member_cannot_change_settings(client, acme, db_session, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    headers = await _member(db_session, session_factory, tenant_id)
    r = await client.put(
        "/admin/tenant/settings",
        json={"require_self_hosted_llm": True, "sensitive_classification": "confidential"},
        headers=headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_rejects_unknown_fields(client, acme) -> None:
    r = await client.put(
        "/admin/tenant/settings",
        json={"require_self_hosted_llm": False, "sensitive_classification": "confidential", "x": 1},
        headers=acme["headers"],
    )
    assert r.status_code == 422
