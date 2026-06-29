"""Starter-template tests: apply seeds content, idempotency, tagging, gating, audit."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.segment import Segment
from app.models.user import User, UserRole
from sqlalchemy import func, select

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
        mid = member.id
    return {"Authorization": f"Bearer {create_access_token(user_id=mid, tenant_id=tenant_id, role='member')}"}


@pytest.mark.asyncio
async def test_list_templates(client, acme) -> None:
    r = await client.get("/admin/templates", headers=acme["headers"])
    assert r.status_code == 200, r.text
    keys = {t["key"] for t in r.json()}
    assert "b2b_saas" in keys
    assert all({"segment_count", "ramp_count", "objection_count"} <= set(t) for t in r.json())


@pytest.mark.asyncio
async def test_apply_template_seeds_tagged_content(client, acme) -> None:
    h = acme["headers"]
    r = await client.post("/admin/templates/apply", json={"template_key": "b2b_saas"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["segments"]["created"] and body["ramp_topics"]["created"]
    assert body["objections"]["created"]

    # Segments + ramp + objections now exist.
    segs = (await client.get("/segments", headers=h)).json()
    assert {"Enterprise", "Mid-Market", "SMB"} <= {s["name"] for s in segs}
    assert (await client.get("/ramp/topics", headers=h)).json()

    # Objections are tagged: filtering by the Enterprise segment returns a subset.
    ent = next(s["id"] for s in segs if s["name"] == "Enterprise")
    ent_objs = (await client.get(f"/objections?segment_id={ent}", headers=h)).json()
    assert ent_objs  # at least one objection tagged Enterprise
    all_objs = (await client.get("/objections", headers=h)).json()
    assert len(ent_objs) <= len(all_objs)


@pytest.mark.asyncio
async def test_apply_template_is_idempotent(client, acme, db_session) -> None:
    h = acme["headers"]
    await client.post("/admin/templates/apply", json={"template_key": "b2b_saas"}, headers=h)
    seg_count_1 = await db_session.scalar(select(func.count()).select_from(Segment))
    # Apply again — everything should be skipped, nothing duplicated.
    again = await client.post(
        "/admin/templates/apply", json={"template_key": "b2b_saas"}, headers=h
    )
    assert again.status_code == 200
    body = again.json()
    assert body["segments"]["created"] == []
    assert body["segments"]["skipped"]
    assert body["objections"]["created"] == []
    seg_count_2 = await db_session.scalar(select(func.count()).select_from(Segment))
    assert seg_count_1 == seg_count_2  # no new segment rows


@pytest.mark.asyncio
async def test_unknown_template_404(client, acme) -> None:
    r = await client.post("/admin/templates/apply", json={"template_key": "nope"}, headers=acme["headers"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_apply_template_manager_only(client, acme, session_factory) -> None:
    ae = await _member_headers(session_factory, uuid.UUID(acme["tenant_id"]))
    r = await client.post("/admin/templates/apply", json={"template_key": "b2b_saas"}, headers=ae)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_apply_template_is_audited(client, acme, db_session) -> None:
    await client.post("/admin/templates/apply", json={"template_key": "smb_velocity"}, headers=acme["headers"])
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.TEMPLATE_APPLIED in actions


@pytest.mark.asyncio
async def test_templates_are_tenant_isolated(client, acme) -> None:
    await client.post("/admin/templates/apply", json={"template_key": "b2b_saas"}, headers=acme["headers"])
    other = await register_tenant(client, "globex", "owner@globex.com")
    # The other tenant sees none of acme's seeded segments.
    assert (await client.get("/segments", headers=other["headers"])).json() == []
