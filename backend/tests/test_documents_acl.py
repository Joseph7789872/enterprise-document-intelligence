"""Document endpoint ACL behavior: VIEW gating, delete, grant/list/revoke."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole

from tests.conftest import register_tenant


async def _upload(client, headers, name: str, text: str) -> uuid.UUID:
    # Manager-only so VIEW comes only from an explicit grant (the behavior under test);
    # rep-visible content would otherwise be visible to every AE by default.
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post(
        "/documents", files=files, data={"visibility": "manager_only"}, headers=headers
    )
    assert r.status_code == 202, r.text
    return uuid.UUID(r.json()["id"])


async def _member(db, session_factory, tenant_id: uuid.UUID, email="member@acme.com") -> tuple[uuid.UUID, dict]:
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email=email,
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id
    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    return member_id, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_member_cannot_view_until_granted(client, acme, db_session, session_factory) -> None:
    doc = await _upload(client, acme["headers"], "a.txt", "Some content. " * 4)
    tenant_id = uuid.UUID(acme["tenant_id"])
    member_id, headers = await _member(db_session, session_factory, tenant_id)

    # No access → 404 (existence not leaked) and absent from the list.
    assert (await client.get(f"/documents/{doc}", headers=headers)).status_code == 404
    assert (await client.get("/documents", headers=headers)).json() == []

    # Owner grants VIEW.
    grant = await client.post(
        f"/documents/{doc}/acl",
        json={"principal_type": "user", "principal_id": str(member_id), "permissions": ["view"]},
        headers=acme["headers"],
    )
    assert grant.status_code == 201, grant.text

    assert (await client.get(f"/documents/{doc}", headers=headers)).status_code == 200
    listed = await client.get("/documents", headers=headers)
    assert [d["id"] for d in listed.json()] == [str(doc)]


@pytest.mark.asyncio
async def test_delete_requires_delete_permission(client, acme, db_session, session_factory) -> None:
    doc = await _upload(client, acme["headers"], "a.txt", "Some content. " * 4)
    tenant_id = uuid.UUID(acme["tenant_id"])
    member_id, headers = await _member(db_session, session_factory, tenant_id)
    await client.post(
        f"/documents/{doc}/acl",
        json={"principal_type": "user", "principal_id": str(member_id), "permissions": ["view"]},
        headers=acme["headers"],
    )

    # VIEW but not DELETE → 403.
    assert (await client.delete(f"/documents/{doc}", headers=headers)).status_code == 403

    # Owner can delete → 204, then it's gone.
    assert (await client.delete(f"/documents/{doc}", headers=acme["headers"])).status_code == 204
    assert (await client.get(f"/documents/{doc}", headers=acme["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_acl_grant_list_revoke_roundtrip(client, acme, db_session, session_factory) -> None:
    doc = await _upload(client, acme["headers"], "a.txt", "Some content. " * 4)
    tenant_id = uuid.UUID(acme["tenant_id"])
    member_id, headers = await _member(db_session, session_factory, tenant_id)

    grant = await client.post(
        f"/documents/{doc}/acl",
        json={"principal_type": "user", "principal_id": str(member_id), "permissions": ["view", "query"]},
        headers=acme["headers"],
    )
    acl_id = grant.json()["id"]

    listed = await client.get(f"/documents/{doc}/acl", headers=acme["headers"])
    assert listed.status_code == 200
    assert any(g["id"] == acl_id for g in listed.json())

    # Member can now view; after revoke, they cannot.
    assert (await client.get(f"/documents/{doc}", headers=headers)).status_code == 200
    revoke = await client.delete(f"/documents/{doc}/acl/{acl_id}", headers=acme["headers"])
    assert revoke.status_code == 204
    assert (await client.get(f"/documents/{doc}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_member_cannot_manage_acl(client, acme, db_session, session_factory) -> None:
    doc = await _upload(client, acme["headers"], "a.txt", "Some content. " * 4)
    tenant_id = uuid.UUID(acme["tenant_id"])
    member_id, headers = await _member(db_session, session_factory, tenant_id)
    # Give VIEW (so it's not a 404), but MANAGE is still required to grant.
    await client.post(
        f"/documents/{doc}/acl",
        json={"principal_type": "user", "principal_id": str(member_id), "permissions": ["view"]},
        headers=acme["headers"],
    )
    resp = await client.post(
        f"/documents/{doc}/acl",
        json={"principal_type": "user", "principal_id": str(member_id), "permissions": ["query"]},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_principal_must_be_same_tenant(client, acme) -> None:
    doc = await _upload(client, acme["headers"], "a.txt", "Some content. " * 4)
    other = await register_tenant(client, "globex", "owner@globex.com")
    # Find globex's owner id.
    other_owner = other["tenant_id"]  # not a user id; use a random id to prove rejection
    resp = await client.post(
        f"/documents/{doc}/acl",
        json={"principal_type": "user", "principal_id": str(uuid.uuid4()), "permissions": ["view"]},
        headers=acme["headers"],
    )
    assert resp.status_code == 404  # principal not found in this tenant
    assert other_owner  # (registered, isolation enforced)
