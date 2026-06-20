"""Query API tests: ask, pending/approve/reject, streaming, isolation, audit."""

from __future__ import annotations

import uuid

import pytest
from app.core.crypto import decrypt_str
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.query import Query, QueryStatus
from app.models.user import User, UserRole
from sqlalchemy import select

from tests.conftest import register_tenant


async def _upload(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text


@pytest.mark.asyncio
async def test_ask_returns_cited_answer(client, acme) -> None:
    await _upload(
        client, acme["headers"], "policy.txt",
        "Remote work is permitted up to three days per week. " * 6,
    )
    r = await client.post("/query", json={"question": "remote work policy?"}, headers=acme["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == QueryStatus.COMPLETED.value
    assert body["answer"]
    assert body["citations"]
    assert body["requires_approval"] is False


@pytest.mark.asyncio
async def test_ask_holds_low_confidence(client, acme) -> None:
    # No documents → empty retrieval → pending approval.
    r = await client.post("/query", json={"question": "what is the policy?"}, headers=acme["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == QueryStatus.PENDING_APPROVAL.value
    assert body["requires_approval"] is True
    assert body["answer"] is None

    # The held query is fetchable and tenant-scoped.
    got = await client.get(f"/query/{body['query_id']}", headers=acme["headers"])
    assert got.status_code == 200
    assert got.json()["status"] == QueryStatus.PENDING_APPROVAL.value


@pytest.mark.asyncio
async def test_stored_question_and_answer_are_encrypted(client, acme, db_session) -> None:
    await _upload(client, acme["headers"], "policy.txt", "Vacation is twenty days per year. " * 6)
    await client.post("/query", json={"question": "vacation days?"}, headers=acme["headers"])
    q = (await db_session.scalars(select(Query))).first()
    assert q is not None
    assert "vacation" not in q.question_encrypted.lower()
    assert decrypt_str(q.question_encrypted) == "vacation days?"
    assert q.answer_encrypted and "[1]" not in q.answer_encrypted  # ciphertext
    assert "[1]" in decrypt_str(q.answer_encrypted)


@pytest.mark.asyncio
async def test_query_is_tenant_isolated(client, acme) -> None:
    await _upload(client, acme["headers"], "secret.txt", "Acme merger plans are confidential. " * 6)
    r = await client.post("/query", json={"question": "vacation?"}, headers=acme["headers"])
    qid = r.json()["query_id"]

    other = await register_tenant(client, "globex", "owner@globex.com")
    cross = await client.get(f"/query/{qid}", headers=other["headers"])
    assert cross.status_code == 404


@pytest.mark.asyncio
async def test_approve_completes_pending_query(client, acme) -> None:
    r = await client.post("/query", json={"question": "anything"}, headers=acme["headers"])
    qid = r.json()["query_id"]
    assert r.json()["status"] == QueryStatus.PENDING_APPROVAL.value

    approved = await client.post(f"/query/{qid}/approve", headers=acme["headers"])
    assert approved.status_code == 200
    assert approved.json()["status"] == QueryStatus.COMPLETED.value
    assert approved.json()["answer"]


@pytest.mark.asyncio
async def test_reject_sets_rejected(client, acme) -> None:
    r = await client.post("/query", json={"question": "anything"}, headers=acme["headers"])
    qid = r.json()["query_id"]
    rejected = await client.post(f"/query/{qid}/reject", headers=acme["headers"])
    assert rejected.status_code == 200
    assert rejected.json()["status"] == QueryStatus.REJECTED.value


@pytest.mark.asyncio
async def test_member_cannot_approve(client, acme, session_factory) -> None:
    r = await client.post("/query", json={"question": "anything"}, headers=acme["headers"])
    qid = r.json()["query_id"]
    tenant_id = uuid.UUID(acme["tenant_id"])

    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id,
            email="member@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER,
            is_active=True,
        )
        s.add(member)
        await s.commit()
        member_id = member.id

    token = create_access_token(user_id=member_id, tenant_id=tenant_id, role="member")
    resp = await client.post(f"/query/{qid}/approve", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_query_emits_audit_and_llm_events(client, acme, db_session) -> None:
    await _upload(client, acme["headers"], "policy.txt", "Remote work allowed three days. " * 6)
    await client.post("/query", json={"question": "remote work?"}, headers=acme["headers"])
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.QUERY_SUBMITTED in actions
    assert AuditAction.QUERY_ANSWERED in actions
    assert AuditAction.LLM_CALL in actions


@pytest.mark.asyncio
async def test_stream_emits_tokens(client, acme) -> None:
    await _upload(client, acme["headers"], "policy.txt", "Remote work allowed three days. " * 6)
    r = await client.post("/query/stream", json={"question": "remote work?"}, headers=acme["headers"])
    assert r.status_code == 200
    assert "event: token" in r.text
    assert "event: done" in r.text
    # The done event carries confidence so the AE UI can surface a "not fully sure" banner.
    assert '"confidence"' in r.text


@pytest.mark.asyncio
async def test_stream_pending_when_no_sources(client, acme) -> None:
    r = await client.post("/query/stream", json={"question": "no docs here"}, headers=acme["headers"])
    assert r.status_code == 200
    assert "event: pending" in r.text


@pytest.mark.asyncio
async def test_query_requires_auth(client) -> None:
    assert (await client.post("/query", json={"question": "x"})).status_code == 401


@pytest.mark.asyncio
async def test_qa_log_lists_own_queries_newest_first(client, acme) -> None:
    await _upload(
        client, acme["headers"], "policy.txt",
        "Remote work is permitted up to three days per week. " * 6,
    )
    await client.post("/query", json={"question": "first remote work question"}, headers=acme["headers"])
    await client.post("/query", json={"question": "second remote work question"}, headers=acme["headers"])

    r = await client.get("/query", headers=acme["headers"])
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= 2
    # Both questions are present and decrypted in the response.
    questions = [q["question"] for q in items]
    assert "first remote work question" in questions
    assert "second remote work question" in questions
    assert {"question", "answer", "citations", "confidence", "status"} <= set(items[0])
    # Ordered newest-first (robust to same-second timestamps: just assert non-increasing).
    dates = [q["created_at"] for q in items]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_qa_log_is_tenant_scoped(client, acme) -> None:
    await client.post("/query", json={"question": "acme private question"}, headers=acme["headers"])
    other = await register_tenant(client, "globex", "owner@globex.com")
    r = await client.get("/query", headers=other["headers"])
    assert r.status_code == 200
    assert "acme private question" not in [q["question"] for q in r.json()]
