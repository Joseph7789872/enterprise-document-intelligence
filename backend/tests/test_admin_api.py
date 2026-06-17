"""Admin API tests: user + group management, role-gating, tenant isolation, audit."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User, UserRole
from sqlalchemy import select


async def _member_headers(db, session_factory, tenant_id: uuid.UUID) -> dict:
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
async def test_admin_creates_and_updates_user(client, acme) -> None:
    created = await client.post(
        "/admin/users",
        json={"email": "analyst@acme.com", "password": "a-strong-password-123", "role": "reviewer"},
        headers=acme["headers"],
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert created.json()["role"] == "reviewer"

    updated = await client.patch(
        f"/admin/users/{user_id}", json={"is_active": False}, headers=acme["headers"]
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    deactivated = await client.delete(f"/admin/users/{user_id}", headers=acme["headers"])
    assert deactivated.status_code == 204


@pytest.mark.asyncio
async def test_duplicate_user_email_conflicts(client, acme) -> None:
    body = {"email": "dup@acme.com", "password": "a-strong-password-123", "role": "member"}
    assert (await client.post("/admin/users", json=body, headers=acme["headers"])).status_code == 201
    assert (await client.post("/admin/users", json=body, headers=acme["headers"])).status_code == 409


@pytest.mark.asyncio
async def test_member_cannot_access_admin(client, acme, db_session, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    headers = await _member_headers(db_session, session_factory, tenant_id)
    assert (await client.get("/admin/users", headers=headers)).status_code == 403
    assert (await client.get("/admin/groups", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_group_lifecycle_with_membership(client, acme) -> None:
    # Create a user to add to the group.
    user = await client.post(
        "/admin/users",
        json={"email": "paralegal@acme.com", "password": "a-strong-password-123", "role": "member"},
        headers=acme["headers"],
    )
    user_id = user.json()["id"]

    group = await client.post(
        "/admin/groups",
        json={"name": "Matter Smith v Jones", "group_type": "matter"},
        headers=acme["headers"],
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]

    listed = await client.get("/admin/groups", headers=acme["headers"])
    assert any(g["id"] == group_id for g in listed.json())

    add = await client.post(
        f"/admin/groups/{group_id}/members", json={"user_id": user_id}, headers=acme["headers"]
    )
    assert add.status_code == 204
    # Idempotent re-add.
    assert (await client.post(
        f"/admin/groups/{group_id}/members", json={"user_id": user_id}, headers=acme["headers"]
    )).status_code == 204

    remove = await client.delete(
        f"/admin/groups/{group_id}/members/{user_id}", headers=acme["headers"]
    )
    assert remove.status_code == 204


@pytest.mark.asyncio
async def test_admin_actions_are_audited(client, acme, db_session) -> None:
    await client.post(
        "/admin/groups", json={"name": "Tax Team", "group_type": "department"},
        headers=acme["headers"],
    )
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.GROUP_CREATED in actions
