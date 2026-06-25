"""Curated-content API tests: ramp topics + saved objections.

AEs (MEMBER) may read; only managers (OWNER/ADMIN) may create/update/delete. Curated
content is tenant-scoped and isolated across tenants.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User, UserRole
from sqlalchemy import select

from tests.conftest import register_tenant


async def _member_headers(session_factory, tenant_id: uuid.UUID) -> dict:
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="ae@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id
    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    return {"Authorization": f"Bearer {token}"}


# ── Ramp topics ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ramp_topic_crud_and_ordering(client, acme) -> None:
    h = acme["headers"]
    first = await client.post(
        "/ramp/topics",
        json={"title": "Pricing", "suggested_question": "How is it priced?", "sort_order": 2},
        headers=h,
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/ramp/topics",
        json={"title": "ICP", "suggested_question": "Who is our ICP?", "sort_order": 1},
        headers=h,
    )
    assert second.status_code == 201

    listed = await client.get("/ramp/topics", headers=h)
    assert listed.status_code == 200
    titles = [t["title"] for t in listed.json()]
    assert titles == ["ICP", "Pricing"]  # ordered by sort_order

    topic_id = second.json()["id"]
    updated = await client.patch(
        f"/ramp/topics/{topic_id}", json={"title": "Ideal customer profile"}, headers=h
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Ideal customer profile"

    deleted = await client.delete(f"/ramp/topics/{topic_id}", headers=h)
    assert deleted.status_code == 204
    remaining = await client.get("/ramp/topics", headers=h)
    assert [t["title"] for t in remaining.json()] == ["Pricing"]


@pytest.mark.asyncio
async def test_ae_can_read_but_not_write_ramp_topics(client, acme, session_factory) -> None:
    await client.post(
        "/ramp/topics",
        json={"title": "Product", "suggested_question": "What does it do?"},
        headers=acme["headers"],
    )
    tenant_id = uuid.UUID(acme["tenant_id"])
    ae = await _member_headers(session_factory, tenant_id)

    # AE can read the curated checklist.
    listed = await client.get("/ramp/topics", headers=ae)
    assert listed.status_code == 200
    assert [t["title"] for t in listed.json()] == ["Product"]

    # But cannot create.
    blocked = await client.post(
        "/ramp/topics",
        json={"title": "Sneaky", "suggested_question": "?"},
        headers=ae,
    )
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_ramp_topics_are_tenant_isolated(client, acme) -> None:
    await client.post(
        "/ramp/topics",
        json={"title": "Acme topic", "suggested_question": "?"},
        headers=acme["headers"],
    )
    other = await register_tenant(client, "globex", "owner@globex.com")
    listed = await client.get("/ramp/topics", headers=other["headers"])
    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.asyncio
async def test_ramp_topic_crud_is_audited(client, acme, db_session) -> None:
    await client.post(
        "/ramp/topics",
        json={"title": "Demo", "suggested_question": "How do I demo?"},
        headers=acme["headers"],
    )
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.RAMP_TOPIC_CREATED in actions


# ── Saved objections ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_objection_crud(client, acme) -> None:
    h = acme["headers"]
    created = await client.post(
        "/objections",
        json={"label": "Too expensive", "prompt": "How do I handle 'too expensive'?"},
        headers=h,
    )
    assert created.status_code == 201, created.text
    obj_id = created.json()["id"]

    listed = await client.get("/objections", headers=h)
    assert [o["label"] for o in listed.json()] == ["Too expensive"]

    updated = await client.patch(
        f"/objections/{obj_id}", json={"prompt": "Handle the price objection."}, headers=h
    )
    assert updated.status_code == 200
    assert updated.json()["prompt"] == "Handle the price objection."

    assert (await client.delete(f"/objections/{obj_id}", headers=h)).status_code == 204
    assert (await client.get("/objections", headers=h)).json() == []


@pytest.mark.asyncio
async def test_ae_can_read_but_not_write_objections(client, acme, session_factory) -> None:
    await client.post(
        "/objections",
        json={"label": "No budget", "prompt": "Handle 'no budget'."},
        headers=acme["headers"],
    )
    tenant_id = uuid.UUID(acme["tenant_id"])
    ae = await _member_headers(session_factory, tenant_id)

    listed = await client.get("/objections", headers=ae)
    assert [o["label"] for o in listed.json()] == ["No budget"]

    blocked = await client.post(
        "/objections", json={"label": "x", "prompt": "y"}, headers=ae
    )
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_objection_not_found_is_tenant_scoped(client, acme) -> None:
    other = await register_tenant(client, "globex", "owner@globex.com")
    created = await client.post(
        "/objections",
        json={"label": "Acme only", "prompt": "?"},
        headers=acme["headers"],
    )
    obj_id = created.json()["id"]
    # Another tenant cannot see or mutate it (404, no existence leak).
    assert (await client.patch(
        f"/objections/{obj_id}", json={"label": "hijack"}, headers=other["headers"]
    )).status_code == 404
