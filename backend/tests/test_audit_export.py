"""Audit export + filtering tests."""

from __future__ import annotations

import json
import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User, UserRole
from sqlalchemy import select


async def _upload(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    assert (await client.post("/documents", files=files, headers=headers)).status_code == 202


@pytest.mark.asyncio
async def test_export_ndjson(client, acme) -> None:
    await _upload(client, acme["headers"], "a.txt", "content " * 5)
    r = await client.get("/audit/export?format=ndjson", headers=acme["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert lines
    row = json.loads(lines[0])
    assert {"id", "action", "created_at", "outcome"} <= set(row)


@pytest.mark.asyncio
async def test_export_csv_has_header(client, acme) -> None:
    await _upload(client, acme["headers"], "a.txt", "content " * 5)
    r = await client.get("/audit/export?format=csv", headers=acme["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("id,created_at,tenant_id")


@pytest.mark.asyncio
async def test_export_is_audited_and_filterable(client, acme, db_session) -> None:
    await _upload(client, acme["headers"], "a.txt", "content " * 5)
    r = await client.get(
        "/audit/export?format=ndjson&action=document.uploaded", headers=acme["headers"]
    )
    assert r.status_code == 200
    for ln in (x for x in r.text.splitlines() if x.strip()):
        assert json.loads(ln)["action"] == "document.uploaded"

    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.AUDIT_EXPORTED in actions


@pytest.mark.asyncio
async def test_export_requires_admin(client, acme, db_session, session_factory) -> None:
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
    r = await client.get("/audit/export", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
