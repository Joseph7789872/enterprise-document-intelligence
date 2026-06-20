"""Retrieval-time ACL enforcement — the headline security guarantee.

A user only ever retrieves chunks from documents they're permitted to QUERY, at
/search and through the agent workflow.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.document_access_control import DocumentAccessControl, PrincipalType
from app.models.query import QueryStatus
from app.models.user import User, UserRole


async def _upload(client, headers, name: str, text: str, visibility: str = "manager_only") -> uuid.UUID:
    # Default manager-only so retrieval-time ACL (the grant path) is what's under test;
    # pass visibility="rep_visible" to exercise the AE default-visibility behavior.
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post(
        "/documents", files=files, data={"visibility": visibility}, headers=headers
    )
    assert r.status_code == 202, r.text
    return uuid.UUID(r.json()["id"])


async def _member(db, session_factory, tenant_id: uuid.UUID) -> tuple[uuid.UUID, dict]:
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="member@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id
    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    return member_id, {"Authorization": f"Bearer {token}"}


async def _grant(db, tenant_id, document_id, user_id, perms) -> None:
    db.add(
        DocumentAccessControl(
            tenant_id=tenant_id, document_id=document_id, principal_type=PrincipalType.USER,
            principal_id=user_id, permissions=perms, granted_by_user_id=user_id,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_member_without_grant_retrieves_nothing(client, acme, db_session, session_factory) -> None:
    await _upload(client, acme["headers"], "secret.txt", "Confidential merger terms here. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    _, headers = await _member(db_session, session_factory, tenant_id)

    r = await client.post("/search", json={"query": "merger terms", "top_k": 6}, headers=headers)
    assert r.status_code == 200
    assert r.json()["results"] == []


@pytest.mark.asyncio
async def test_search_returns_only_permitted_documents(client, acme, db_session, session_factory) -> None:
    doc_a = await _upload(client, acme["headers"], "hr.txt", "Vacation policy grants twenty days. " * 5)
    doc_b = await _upload(client, acme["headers"], "ops.txt", "Logistics shipment cold chain rules. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    member_id, headers = await _member(db_session, session_factory, tenant_id)

    # Grant QUERY on doc A only.
    await _grant(db_session, tenant_id, doc_a, member_id, ["query"])

    # Even when searching for doc B's content, doc B never surfaces.
    r = await client.post("/search", json={"query": "logistics shipment cold chain", "top_k": 6}, headers=headers)
    assert r.status_code == 200
    returned_docs = {res["document_id"] for res in r.json()["results"]}
    assert str(doc_b) not in returned_docs
    assert returned_docs <= {str(doc_a)}


@pytest.mark.asyncio
async def test_member_retrieves_rep_visible_without_grant(client, acme, db_session, session_factory) -> None:
    # Rep-visible content is queryable by any AE without an explicit grant.
    await _upload(
        client, acme["headers"], "pitch.txt",
        "Our product pitch covers onboarding and analytics. " * 5, "rep_visible",
    )
    tenant_id = uuid.UUID(acme["tenant_id"])
    _, headers = await _member(db_session, session_factory, tenant_id)

    r = await client.post("/search", json={"query": "product pitch onboarding", "top_k": 6}, headers=headers)
    assert r.status_code == 200
    assert r.json()["results"]  # the AE can see rep-visible content


@pytest.mark.asyncio
async def test_low_confidence_answers_when_human_review_disabled(
    client, acme, db_session, session_factory, monkeypatch
) -> None:
    # With the human-review gate off (the v1 default), an empty/low-confidence retrieval
    # is answered honestly rather than held for a human.
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_HUMAN_REVIEW", False, raising=False)
    await _upload(client, acme["headers"], "secret.txt", "Manager-only floor pricing memo. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    _, headers = await _member(db_session, session_factory, tenant_id)

    r = await client.post("/query", json={"question": "floor pricing?"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == QueryStatus.COMPLETED.value
    assert r.json()["answer"] is not None


@pytest.mark.asyncio
async def test_owner_sees_all_documents(client, acme) -> None:
    await _upload(client, acme["headers"], "a.txt", "Alpha vacation policy content. " * 5)
    r = await client.post("/search", json={"query": "vacation policy", "top_k": 6}, headers=acme["headers"])
    assert r.status_code == 200
    assert r.json()["results"]  # owner is unrestricted


@pytest.mark.asyncio
async def test_member_query_without_access_is_held(client, acme, db_session, session_factory) -> None:
    await _upload(client, acme["headers"], "secret.txt", "Privileged client strategy memo. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    _, headers = await _member(db_session, session_factory, tenant_id)

    # No grants → empty retrieval → low confidence → pending approval (never auto-answered).
    r = await client.post("/query", json={"question": "client strategy?"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == QueryStatus.PENDING_APPROVAL.value
    assert r.json()["answer"] is None
