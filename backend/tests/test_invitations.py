"""Invitation flow: invite emails a link, accept creates an active user, edge cases, gating."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User, UserRole
from app.services.email import sender
from app.services.email.sender import FakeEmailSender
from sqlalchemy import select

from tests.conftest import register_tenant


@pytest.fixture
def outbox() -> Iterator[FakeEmailSender]:
    fake = FakeEmailSender()
    sender.set_email_sender(fake)
    yield fake
    sender.set_email_sender(None)


def _token_from_outbox(fake: FakeEmailSender) -> str:
    assert fake.outbox, "expected an email to have been sent"
    link = next(line for line in fake.outbox[-1].text.splitlines() if "accept-invite" in line)
    return parse_qs(urlparse(link.strip()).query)["token"][0]


async def _member_headers(session_factory, tenant_id: uuid.UUID) -> dict:
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="ae@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        mid = member.id
    return {"Authorization": f"Bearer {create_access_token(user_id=mid, tenant_id=tenant_id, role='member')}"}


@pytest.mark.asyncio
async def test_invite_then_accept_creates_active_user(client, acme, outbox, db_session) -> None:
    h = acme["headers"]
    r = await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=h)
    assert r.status_code == 201, r.text
    token = _token_from_outbox(outbox)

    acc = await client.post("/auth/accept-invite", json={"token": token, "password": "brand-new-password-1"})
    assert acc.status_code == 201, acc.text
    body = acc.json()
    assert body["tenant_id"] == acme["tenant_id"]
    # The returned token authenticates as the new rep.
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "rep@acme.com"
    assert me.json()["role"] == "member"

    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.USER_INVITED in actions
    assert AuditAction.INVITE_ACCEPTED in actions


@pytest.mark.asyncio
async def test_accept_is_single_use(client, acme, outbox) -> None:
    h = acme["headers"]
    await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=h)
    token = _token_from_outbox(outbox)
    first = await client.post("/auth/accept-invite", json={"token": token, "password": "brand-new-password-1"})
    assert first.status_code == 201
    again = await client.post("/auth/accept-invite", json={"token": token, "password": "another-password-99"})
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_accept_garbage_token_400(client, acme) -> None:
    r = await client.post("/auth/accept-invite", json={"token": "not-a-real-token", "password": "password-1234567"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_pending_invite_409(client, acme, outbox) -> None:
    h = acme["headers"]
    first = await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=h)
    assert first.status_code == 201
    dup = await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=h)
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_invite_existing_user_409(client, acme, outbox, session_factory) -> None:
    await _member_headers(session_factory, uuid.UUID(acme["tenant_id"]))
    r = await client.post("/admin/invitations", json={"email": "ae@acme.com", "role": "member"}, headers=acme["headers"])
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_invite_manager_only(client, acme, session_factory) -> None:
    ae = await _member_headers(session_factory, uuid.UUID(acme["tenant_id"]))
    r = await client.post("/admin/invitations", json={"email": "x@acme.com", "role": "member"}, headers=ae)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_revoke_invitation(client, acme, outbox) -> None:
    h = acme["headers"]
    r = await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=h)
    inv_id = r.json()["id"]
    listed = await client.get("/admin/invitations", headers=h)
    assert any(i["id"] == inv_id for i in listed.json())
    rev = await client.delete(f"/admin/invitations/{inv_id}", headers=h)
    assert rev.status_code == 204
    listed2 = await client.get("/admin/invitations", headers=h)
    assert all(i["id"] != inv_id for i in listed2.json())


@pytest.mark.asyncio
async def test_invitations_are_tenant_isolated(client, acme, outbox) -> None:
    await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"])
    other = await register_tenant(client, "globex", "owner@globex.com")
    assert (await client.get("/admin/invitations", headers=other["headers"])).json() == []
