"""Reviewer approval scoping: a REVIEWER needs CanReview on the source documents."""

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


async def _reviewer(db, session_factory, tenant_id: uuid.UUID) -> tuple[uuid.UUID, dict]:
    async with session_factory() as s:
        reviewer = User(
            tenant_id=tenant_id, email="reviewer@acme.com",
            hashed_password=hash_password("password-reviewerx"),
            role=UserRole.REVIEWER, is_active=True,
        )
        s.add(reviewer)
        await s.commit()
        reviewer_id = reviewer.id
    token = create_access_token(user_id=reviewer_id, tenant_id=tenant_id, role="reviewer")
    return reviewer_id, {"Authorization": f"Bearer {token}"}


async def _held_query(client, owner_headers) -> str:
    # The [lowconf] marker forces the FakeLLM verifier low → human review (held).
    r = await client.post(
        "/query", json={"question": "[lowconf] vacation policy"}, headers=owner_headers
    )
    assert r.json()["status"] == QueryStatus.PENDING_APPROVAL.value
    return r.json()["query_id"]


@pytest.mark.asyncio
async def test_reviewer_without_canreview_is_denied(client, acme, db_session, session_factory) -> None:
    await _upload(client, acme["headers"], "hr.txt", "Vacation policy grants twenty days. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    qid = await _held_query(client, acme["headers"])
    _, headers = await _reviewer(db_session, session_factory, tenant_id)

    resp = await client.post(f"/query/{qid}/approve", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reviewer_with_canreview_can_approve(client, acme, db_session, session_factory) -> None:
    doc = await _upload(client, acme["headers"], "hr.txt", "Vacation policy grants twenty days. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    qid = await _held_query(client, acme["headers"])
    reviewer_id, headers = await _reviewer(db_session, session_factory, tenant_id)

    # Owner grants the reviewer REVIEW on the source document.
    grant = await client.post(
        f"/documents/{doc}/acl",
        json={"principal_type": "user", "principal_id": str(reviewer_id), "permissions": ["review"]},
        headers=acme["headers"],
    )
    assert grant.status_code == 201, grant.text

    resp = await client.post(f"/query/{qid}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == QueryStatus.COMPLETED.value
    assert resp.json()["answer"]


@pytest.mark.asyncio
async def test_admin_can_approve_without_grant(client, acme) -> None:
    await _upload(client, acme["headers"], "hr.txt", "Vacation policy grants twenty days. " * 5)
    qid = await _held_query(client, acme["headers"])
    # The owner (privileged) approves with no per-doc grant needed.
    resp = await client.post(f"/query/{qid}/approve", headers=acme["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == QueryStatus.COMPLETED.value
