"""Password reset: forgot emails a link, reset changes the password, no enumeration, edges."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from app.services.email import sender
from app.services.email.sender import FakeEmailSender


@pytest.fixture
def outbox() -> Iterator[FakeEmailSender]:
    fake = FakeEmailSender()
    sender.set_email_sender(fake)
    yield fake
    sender.set_email_sender(None)


def _reset_token(fake: FakeEmailSender) -> str:
    link = next(line for line in fake.outbox[-1].text.splitlines() if "reset-password" in line)
    return parse_qs(urlparse(link.strip()).query)["token"][0]


@pytest.mark.asyncio
async def test_forgot_then_reset_changes_password(client, acme, outbox) -> None:
    # acme owner is owner@acme.com with the conftest default password.
    r = await client.post(
        "/auth/forgot-password", json={"tenant_slug": "acme-legal", "email": "owner@acme.com"}
    )
    assert r.status_code == 202
    token = _reset_token(outbox)

    new_password = "a-totally-new-password-2"
    rs = await client.post("/auth/reset-password", json={"token": token, "new_password": new_password})
    assert rs.status_code == 200

    # New password logs in; old one no longer works.
    ok = await client.post(
        "/auth/login",
        json={"tenant_slug": "acme-legal", "email": "owner@acme.com", "password": new_password},
    )
    assert ok.status_code == 200
    old = await client.post(
        "/auth/login",
        json={"tenant_slug": "acme-legal", "email": "owner@acme.com", "password": "correct horse battery staple"},
    )
    assert old.status_code == 401


@pytest.mark.asyncio
async def test_forgot_unknown_email_no_enumeration(client, acme, outbox) -> None:
    r = await client.post(
        "/auth/forgot-password", json={"tenant_slug": "acme-legal", "email": "nobody@acme.com"}
    )
    assert r.status_code == 202  # same response as a real account
    assert outbox.outbox == []   # but no email is sent


@pytest.mark.asyncio
async def test_reset_token_is_single_use(client, acme, outbox) -> None:
    await client.post("/auth/forgot-password", json={"tenant_slug": "acme-legal", "email": "owner@acme.com"})
    token = _reset_token(outbox)
    first = await client.post("/auth/reset-password", json={"token": token, "new_password": "first-new-password-1"})
    assert first.status_code == 200
    again = await client.post("/auth/reset-password", json={"token": token, "new_password": "second-new-password-2"})
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_reset_garbage_token_400(client, acme) -> None:
    r = await client.post("/auth/reset-password", json={"token": "bogus", "new_password": "password-1234567"})
    assert r.status_code == 400
