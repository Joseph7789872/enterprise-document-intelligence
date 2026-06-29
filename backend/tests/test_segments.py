"""Segment (ICP) API tests: managed list CRUD + tagging content/objections + filtering.

AEs (MEMBER) may read segments and filter objections; only managers (OWNER/ADMIN) may
create/update/delete segments and tag content. Segments are tenant-scoped + isolated.
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


async def _make_segment(client, headers, name: str, sort_order: int = 0) -> str:
    r = await client.post(
        "/segments", json={"name": name, "sort_order": sort_order}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── CRUD + ordering ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_segment_crud_and_ordering(client, acme) -> None:
    h = acme["headers"]
    await _make_segment(client, h, "Enterprise", sort_order=2)
    smb = await _make_segment(client, h, "SMB", sort_order=1)

    listed = await client.get("/segments", headers=h)
    assert listed.status_code == 200
    assert [s["name"] for s in listed.json()] == ["SMB", "Enterprise"]  # by sort_order

    updated = await client.patch(f"/segments/{smb}", json={"name": "Small Business"}, headers=h)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Small Business"

    assert (await client.delete(f"/segments/{smb}", headers=h)).status_code == 204
    remaining = await client.get("/segments", headers=h)
    assert [s["name"] for s in remaining.json()] == ["Enterprise"]


@pytest.mark.asyncio
async def test_duplicate_segment_name_conflicts(client, acme) -> None:
    await _make_segment(client, acme["headers"], "Healthcare")
    dup = await client.post("/segments", json={"name": "Healthcare"}, headers=acme["headers"])
    assert dup.status_code == 409, dup.text


@pytest.mark.asyncio
async def test_ae_can_read_but_not_write_segments(client, acme, session_factory) -> None:
    await _make_segment(client, acme["headers"], "Enterprise")
    ae = await _member_headers(session_factory, uuid.UUID(acme["tenant_id"]))

    listed = await client.get("/segments", headers=ae)
    assert [s["name"] for s in listed.json()] == ["Enterprise"]
    blocked = await client.post("/segments", json={"name": "Sneaky"}, headers=ae)
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_segments_are_tenant_isolated(client, acme) -> None:
    await _make_segment(client, acme["headers"], "Acme segment")
    other = await register_tenant(client, "globex", "owner@globex.com")
    assert (await client.get("/segments", headers=other["headers"])).json() == []


@pytest.mark.asyncio
async def test_segment_crud_is_audited(client, acme, db_session) -> None:
    await _make_segment(client, acme["headers"], "Audited")
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.SEGMENT_CREATED in actions


# ── Objection tagging + filtering ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_objection_tagging_and_segment_filter(client, acme) -> None:
    h = acme["headers"]
    ent = await _make_segment(client, h, "Enterprise")
    smb = await _make_segment(client, h, "SMB")

    # An objection tagged Enterprise...
    created = await client.post(
        "/objections",
        json={"label": "Security review", "prompt": "Handle the security objection.",
              "segment_ids": [ent]},
        headers=h,
    )
    assert created.status_code == 201, created.text
    assert created.json()["segment_ids"] == [ent]
    # ...and one tagged SMB.
    await client.post(
        "/objections",
        json={"label": "Price", "prompt": "Handle price.", "segment_ids": [smb]},
        headers=h,
    )

    # Unfiltered list returns both.
    all_objs = await client.get("/objections", headers=h)
    assert {o["label"] for o in all_objs.json()} == {"Security review", "Price"}

    # Filtered by Enterprise returns only the tagged one.
    filtered = await client.get(f"/objections?segment_id={ent}", headers=h)
    assert [o["label"] for o in filtered.json()] == ["Security review"]


@pytest.mark.asyncio
async def test_objection_retag_via_update(client, acme) -> None:
    h = acme["headers"]
    ent = await _make_segment(client, h, "Enterprise")
    created = await client.post(
        "/objections", json={"label": "X", "prompt": "y"}, headers=h
    )
    obj_id = created.json()["id"]
    assert created.json()["segment_ids"] == []

    tagged = await client.patch(
        f"/objections/{obj_id}", json={"segment_ids": [ent]}, headers=h
    )
    assert tagged.json()["segment_ids"] == [ent]
    # Clearing with [] removes tags.
    cleared = await client.patch(f"/objections/{obj_id}", json={"segment_ids": []}, headers=h)
    assert cleared.json()["segment_ids"] == []


@pytest.mark.asyncio
async def test_tagging_with_foreign_segment_is_rejected(client, acme) -> None:
    """A segment from another tenant cannot be used to tag content (404)."""
    other = await register_tenant(client, "globex", "owner@globex.com")
    foreign = await _make_segment(client, other["headers"], "Globex only")
    blocked = await client.post(
        "/objections",
        json={"label": "X", "prompt": "y", "segment_ids": [foreign]},
        headers=acme["headers"],
    )
    assert blocked.status_code == 404, blocked.text


# ── Document tagging + segment-scoped retrieval ────────────────────────────────────────
async def _upload(client, headers, name: str, text: str, segment_ids: list[str] | None = None):
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    data = {"segment_ids": segment_ids} if segment_ids else None
    r = await client.post("/documents", files=files, data=data, headers=headers)
    assert r.status_code == 202, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_document_tagging_on_upload_and_retag(client, acme) -> None:
    h = acme["headers"]
    ent = await _make_segment(client, h, "Enterprise")
    smb = await _make_segment(client, h, "SMB")
    doc_id = await _upload(client, h, "battlecard.txt", "Enterprise wins. " * 6, [ent])

    got = await client.get(f"/documents/{doc_id}", headers=h)
    assert got.json()["segment_ids"] == [ent]

    retag = await client.put(
        f"/documents/{doc_id}/segments", json={"segment_ids": [smb]}, headers=h
    )
    assert retag.status_code == 200
    assert retag.json()["segment_ids"] == [smb]


@pytest.mark.asyncio
async def test_segment_scoped_search_intersects_with_acl(client, acme) -> None:
    h = acme["headers"]
    ent = await _make_segment(client, h, "Enterprise")
    await _upload(client, h, "ent.txt", "Enterprise pricing is custom and negotiated. " * 6, [ent])
    await _upload(client, h, "smb.txt", "SMB pricing is self-serve and fixed. " * 6, None)

    # Scoped to Enterprise: only the tagged doc can surface.
    scoped = await client.post(
        "/search", json={"query": "pricing", "top_k": 5, "segment_id": ent}, headers=h
    )
    assert scoped.status_code == 200, scoped.text
    files = {r["filename"] for r in scoped.json()["results"]}
    assert files <= {"ent.txt"}
    assert "smb.txt" not in files
