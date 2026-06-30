"""Invitation flow: invite returns a key, accept (slug+email+key) creates a user, gating."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

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


ACME_SLUG = "acme-legal"  # the slug the `acme` fixture registers


async def _accept(client, slug: str, email: str, key: str, password: str):
    return await client.post(
        "/auth/accept-invite",
        json={"tenant_slug": slug, "email": email, "invite_key": key, "password": password},
    )


class _FailingEmailSender:
    """Simulates an unconfigured/broken mail provider."""

    async def send(self, msg: object) -> None:  # noqa: ANN401 - test double
        raise RuntimeError("smtp down")


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
async def test_invite_then_accept_creates_active_user(client, acme, db_session) -> None:
    h = acme["headers"]
    r = await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=h)
    assert r.status_code == 201, r.text
    key = r.json()["invite_key"]
    assert r.json()["tenant_slug"] == ACME_SLUG

    acc = await _accept(client, ACME_SLUG, "rep@acme.com", key, "brand-new-password-1")
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
async def test_create_returns_shareable_key(client, acme) -> None:
    # The invite key is returned directly (no email needed) and accepting with it works.
    r = await client.post(
        "/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"]
    )
    assert r.status_code == 201, r.text
    key = r.json()["invite_key"]
    assert "-" in key  # human-readable grouped key
    acc = await _accept(client, ACME_SLUG, "rep@acme.com", key, "brand-new-password-1")
    assert acc.status_code == 201, acc.text


@pytest.mark.asyncio
async def test_key_is_normalized_on_accept(client, acme) -> None:
    # Dashes/case/whitespace don't matter — the key is normalized before verifying.
    r = await client.post(
        "/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"]
    )
    key = r.json()["invite_key"]
    messy = f"  {key.replace('-', '').lower()} "
    acc = await _accept(client, ACME_SLUG, "rep@acme.com", messy, "brand-new-password-1")
    assert acc.status_code == 201, acc.text


@pytest.mark.asyncio
async def test_wrong_key_rejected(client, acme) -> None:
    await client.post(
        "/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"]
    )
    acc = await _accept(client, ACME_SLUG, "rep@acme.com", "WRONG-KEY22-WRONG-KEY22", "password-1234567")
    assert acc.status_code == 400


@pytest.mark.asyncio
async def test_regenerate_key_invalidates_old_one(client, acme) -> None:
    r = await client.post(
        "/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"]
    )
    inv_id = r.json()["id"]
    old_key = r.json()["invite_key"]

    regen = await client.post(f"/admin/invitations/{inv_id}/link", headers=acme["headers"])
    assert regen.status_code == 200, regen.text
    new_key = regen.json()["invite_key"]
    assert new_key != old_key

    # Old key no longer works; the freshly minted one does.
    stale = await _accept(client, ACME_SLUG, "rep@acme.com", old_key, "password-old-1234")
    assert stale.status_code == 400
    ok = await _accept(client, ACME_SLUG, "rep@acme.com", new_key, "password-new-1234")
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_invite_succeeds_when_email_fails(client, acme) -> None:
    # A broken/unconfigured mail provider must not break invites — the key is still returned.
    sender.set_email_sender(_FailingEmailSender())
    try:
        r = await client.post(
            "/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"]
        )
        assert r.status_code == 201, r.text
        key = r.json()["invite_key"]
        acc = await _accept(client, ACME_SLUG, "rep@acme.com", key, "brand-new-password-1")
        assert acc.status_code == 201
    finally:
        sender.set_email_sender(None)


@pytest.mark.asyncio
async def test_regenerate_link_requires_manager(client, acme, session_factory) -> None:
    r = await client.post(
        "/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"]
    )
    inv_id = r.json()["id"]
    ae = await _member_headers(session_factory, uuid.UUID(acme["tenant_id"]))
    denied = await client.post(f"/admin/invitations/{inv_id}/link", headers=ae)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_accept_is_single_use(client, acme) -> None:
    h = acme["headers"]
    r = await client.post("/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=h)
    key = r.json()["invite_key"]
    first = await _accept(client, ACME_SLUG, "rep@acme.com", key, "brand-new-password-1")
    assert first.status_code == 201
    again = await _accept(client, ACME_SLUG, "rep@acme.com", key, "another-password-99")
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_accept_unknown_invite_400(client, acme) -> None:
    # Valid-looking workspace but no pending invite for this email → generic 400.
    r = await _accept(client, ACME_SLUG, "nobody@acme.com", "ABCDE-FGHJK-LMNPQ-RSTUV", "password-1234567")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_accept_unknown_workspace_400(client, acme) -> None:
    r = await _accept(client, "no-such-workspace", "rep@acme.com", "ABCDE-FGHJK-LMNPQ-RSTUV", "password-1234567")
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
