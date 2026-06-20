"""Approval authorization: only managers (OWNER/ADMIN) may approve a held query.

The human-approval gate is off by default in the v1 sales product, but the endpoint is
retained; these tests cover its authorization. (The dedicated REVIEWER role + per-document
REVIEW scoping were removed in the v1 two-role reframe.)
"""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.query import QueryStatus
from app.models.user import User, UserRole


async def _upload(client, headers, name: str, text: str) -> uuid.UUID:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text
    return uuid.UUID(r.json()["id"])


async def _member(db, session_factory, tenant_id: uuid.UUID) -> dict:
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


async def _held_query(client, owner_headers) -> str:
    # The [lowconf] marker forces the FakeLLM verifier low → human review (held).
    r = await client.post(
        "/query", json={"question": "[lowconf] vacation policy"}, headers=owner_headers
    )
    assert r.json()["status"] == QueryStatus.PENDING_APPROVAL.value
    return r.json()["query_id"]


@pytest.mark.asyncio
async def test_manager_can_approve_held_query(client, acme) -> None:
    await _upload(client, acme["headers"], "hr.txt", "Vacation policy grants twenty days. " * 5)
    qid = await _held_query(client, acme["headers"])
    # The owner (a manager) approves with no per-doc grant needed.
    resp = await client.post(f"/query/{qid}/approve", headers=acme["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == QueryStatus.COMPLETED.value
    assert resp.json()["answer"]


@pytest.mark.asyncio
async def test_ae_cannot_approve(client, acme, db_session, session_factory) -> None:
    await _upload(client, acme["headers"], "hr.txt", "Vacation policy grants twenty days. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    qid = await _held_query(client, acme["headers"])
    ae_headers = await _member(db_session, session_factory, tenant_id)

    resp = await client.post(f"/query/{qid}/approve", headers=ae_headers)
    assert resp.status_code == 403
