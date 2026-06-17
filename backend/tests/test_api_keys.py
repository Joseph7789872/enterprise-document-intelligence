"""API key tests: issue/authenticate/revoke + admin endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.user import User, UserRole
from app.services import api_key_service
from sqlalchemy import select


async def _owner_id(db, tenant_id: uuid.UUID) -> uuid.UUID:
    owner = (
        await db.scalars(
            select(User).where(User.tenant_id == tenant_id, User.role == UserRole.OWNER)
        )
    ).first()
    return owner.id


@pytest.mark.asyncio
async def test_issue_and_authenticate_roundtrip(client, acme, db_session) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    owner_id = await _owner_id(db_session, tenant_id)
    api_key, full_key = await api_key_service.issue(
        db_session, tenant_id=tenant_id, user_id=owner_id, name="k", scopes=["query"],
    )
    await db_session.commit()
    assert full_key.startswith("edip_")
    assert "." in full_key  # prefix.secret

    principal = await api_key_service.authenticate(db_session, full_key)
    assert principal is not None
    assert principal.id == owner_id
    assert principal.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_wrong_key_rejected(client, acme, db_session) -> None:
    assert await api_key_service.authenticate(db_session, "edip_deadbeef.nope") is None
    assert await api_key_service.authenticate(db_session, "garbage") is None


@pytest.mark.asyncio
async def test_revoked_and_expired_rejected(client, acme, db_session) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    owner_id = await _owner_id(db_session, tenant_id)

    revoked, key1 = await api_key_service.issue(
        db_session, tenant_id=tenant_id, user_id=owner_id, name="r", scopes=["query"],
    )
    revoked.revoked_at = datetime.now(UTC)
    expired, key2 = await api_key_service.issue(
        db_session, tenant_id=tenant_id, user_id=owner_id, name="e", scopes=["query"],
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await db_session.commit()

    assert await api_key_service.authenticate(db_session, key1) is None
    assert await api_key_service.authenticate(db_session, key2) is None


@pytest.mark.asyncio
async def test_admin_create_list_revoke(client, acme) -> None:
    created = await client.post(
        "/admin/api-keys", json={"name": "ci-key", "scopes": ["query", "search"]},
        headers=acme["headers"],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["key"].startswith("edip_")  # plaintext returned once
    key_id = body["id"]

    listed = await client.get("/admin/api-keys", headers=acme["headers"])
    assert any(k["id"] == key_id for k in listed.json())
    assert all("key" not in k for k in listed.json())  # secret never re-exposed

    assert (await client.delete(f"/admin/api-keys/{key_id}", headers=acme["headers"])).status_code == 204


@pytest.mark.asyncio
async def test_member_cannot_create_api_key(client, acme, db_session, session_factory) -> None:
    from app.core.security import create_access_token, hash_password

    tenant_id = uuid.UUID(acme["tenant_id"])
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="member@acme.com",
            hashed_password=hash_password("password-memberx"), role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id
    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    resp = await client.post(
        "/admin/api-keys", json={"name": "x"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
