"""Compliance + GDPR DSR tests."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.query import Query
from app.models.user import User, UserRole
from sqlalchemy import select


async def _member(db, session_factory, tenant_id: uuid.UUID, email="subject@acme.com") -> tuple[uuid.UUID, dict]:
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email=email,
            hashed_password=hash_password("password-memberx"), role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id
    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    return member_id, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_compliance_config(client, acme) -> None:
    r = await client.get("/compliance/config", headers=acme["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["data_region"]
    assert body["append_only_audit"] is True
    assert body["langfuse_io_capture"] is False
    # No secrets leak through the config snapshot.
    assert "secret" not in r.text.lower()


@pytest.mark.asyncio
async def test_config_requires_admin(client, acme, db_session, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    _, headers = await _member(db_session, session_factory, tenant_id)
    assert (await client.get("/compliance/config", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_retention_upsert(client, acme) -> None:
    put = await client.put(
        "/compliance/retention",
        json={"resource_type": "document", "retention_days": 365},
        headers=acme["headers"],
    )
    assert put.status_code == 200
    listed = await client.get("/compliance/retention", headers=acme["headers"])
    assert any(p["resource_type"] == "document" for p in listed.json())


@pytest.mark.asyncio
async def test_dsr_export_bundle(client, acme, db_session, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    _, headers = await _member(db_session, session_factory, tenant_id)
    # The subject runs a query so there's data to export.
    await client.post("/query", json={"question": "anything"}, headers=headers)

    created = await client.post(
        "/compliance/ds-request",
        json={"subject_email": "subject@acme.com", "request_type": "export"},
        headers=acme["headers"],
    )
    assert created.status_code == 201, created.text
    dsr_id = created.json()["id"]

    fulfilled = await client.post(
        f"/compliance/ds-request/{dsr_id}/fulfill", headers=acme["headers"]
    )
    assert fulfilled.status_code == 200
    result = fulfilled.json()["result"]
    assert result["user"]["email"] == "subject@acme.com"
    assert len(result["queries"]) >= 1


@pytest.mark.asyncio
async def test_dsr_erasure_deletes_queries_but_keeps_audit(client, acme, db_session, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    member_id, headers = await _member(db_session, session_factory, tenant_id)
    await client.post("/query", json={"question": "anything"}, headers=headers)

    audit_before = len((await db_session.scalars(select(AuditLog.id))).all())

    created = await client.post(
        "/compliance/ds-request",
        json={"subject_email": "subject@acme.com", "request_type": "erasure"},
        headers=acme["headers"],
    )
    dsr_id = created.json()["id"]
    fulfilled = await client.post(
        f"/compliance/ds-request/{dsr_id}/fulfill", headers=acme["headers"]
    )
    assert fulfilled.status_code == 200
    assert fulfilled.json()["result"]["audit_logs_retained"] is True

    # The subject's queries are gone…
    remaining = (
        await db_session.scalars(select(Query).where(Query.user_id == member_id))
    ).all()
    assert remaining == []
    # …but audit history is retained (immutable).
    audit_after = len((await db_session.scalars(select(AuditLog.id))).all())
    assert audit_after >= audit_before
    # …and the user record is anonymized.
    user = await db_session.get(User, member_id)
    assert user.email.startswith("erased-")
    assert AuditAction.DSR_FULFILLED in (await db_session.scalars(select(AuditLog.action))).all()
