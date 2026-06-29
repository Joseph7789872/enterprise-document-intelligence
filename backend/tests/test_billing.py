"""Billing: overview/usage, plan-limit enforcement (seats/docs/queries), checkout, webhook."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.core.config import settings
from app.services import plans_data
from app.services.email import sender
from app.services.email.sender import FakeEmailSender
from app.services.plans_data import Plan, PlanLimits


@pytest.fixture
def outbox() -> Iterator[FakeEmailSender]:
    fake = FakeEmailSender()
    sender.set_email_sender(fake)
    yield fake
    sender.set_email_sender(None)


def _tiny_trial(monkeypatch, *, seats=3, documents=25, queries=200) -> None:
    monkeypatch.setitem(
        plans_data.PLANS,
        "trial",
        Plan(
            key="trial", name="Trial", price_display="Free",
            limits=PlanLimits(seats=seats, documents=documents, queries_per_month=queries),
        ),
    )


def _doc(name: str, text: str) -> dict:
    return {"file": (name, text.encode("utf-8"), "text/plain")}


@pytest.mark.asyncio
async def test_billing_overview_shows_trial_and_usage(client, acme) -> None:
    r = await client.get("/billing", headers=acme["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subscription"]["plan_key"] == "trial"
    assert body["plan"]["key"] == "trial"
    assert body["usage"]["users"] == 1  # the owner


@pytest.mark.asyncio
async def test_list_plans(client, acme) -> None:
    r = await client.get("/billing/plans", headers=acme["headers"])
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    assert {"trial", "pro", "business"} <= keys


@pytest.mark.asyncio
async def test_seat_limit_blocks_invite(client, acme, monkeypatch, outbox) -> None:
    _tiny_trial(monkeypatch, seats=1)  # the owner already fills the single seat
    r = await client.post(
        "/admin/invitations", json={"email": "rep@acme.com", "role": "member"}, headers=acme["headers"]
    )
    assert r.status_code == 402, r.text


@pytest.mark.asyncio
async def test_document_limit_blocks_upload(client, acme, monkeypatch) -> None:
    _tiny_trial(monkeypatch, documents=1)
    first = await client.post("/documents", files=_doc("a.txt", "Content one. " * 6), headers=acme["headers"])
    assert first.status_code == 202, first.text
    second = await client.post("/documents", files=_doc("b.txt", "Content two. " * 6), headers=acme["headers"])
    assert second.status_code == 402


@pytest.mark.asyncio
async def test_query_limit_blocks_ask(client, acme, monkeypatch) -> None:
    _tiny_trial(monkeypatch, queries=1)
    first = await client.post("/query", json={"question": "What is our pricing?"}, headers=acme["headers"])
    assert first.status_code == 200, first.text
    second = await client.post("/query", json={"question": "What about discounts?"}, headers=acme["headers"])
    assert second.status_code == 402


@pytest.mark.asyncio
async def test_no_limits_when_billing_disabled(client, acme, monkeypatch) -> None:
    _tiny_trial(monkeypatch, documents=1)
    monkeypatch.setattr(settings, "ENABLE_BILLING", False)
    first = await client.post("/documents", files=_doc("a.txt", "Content one. " * 6), headers=acme["headers"])
    second = await client.post("/documents", files=_doc("b.txt", "Content two. " * 6), headers=acme["headers"])
    assert first.status_code == 202
    assert second.status_code == 202  # no enforcement when billing is off


@pytest.mark.asyncio
async def test_checkout_returns_url(client, acme) -> None:
    r = await client.post("/billing/checkout", json={"plan_key": "pro"}, headers=acme["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"].startswith("http")


@pytest.mark.asyncio
async def test_checkout_manager_only(client, acme, session_factory) -> None:
    import uuid

    from app.core.security import create_access_token, hash_password
    from app.models.user import User, UserRole

    tenant_id = uuid.UUID(acme["tenant_id"])
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="ae@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        mid = member.id
    ae = {"Authorization": f"Bearer {create_access_token(user_id=mid, tenant_id=tenant_id, role='member')}"}
    r = await client.post("/billing/checkout", json={"plan_key": "pro"}, headers=ae)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_webhook_upgrades_subscription(client, acme) -> None:
    payload = {"tenant_id": acme["tenant_id"], "plan_key": "pro", "status": "active"}
    wh = await client.post("/billing/webhook", json=payload)
    assert wh.status_code == 200, wh.text
    overview = await client.get("/billing", headers=acme["headers"])
    assert overview.json()["subscription"]["plan_key"] == "pro"
    assert overview.json()["subscription"]["status"] == "active"
