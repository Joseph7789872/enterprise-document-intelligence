"""Manager analytics: overview aggregation, low-confidence drill-down, gating, isolation."""

from __future__ import annotations

import uuid

import pytest
from app.core.crypto import encrypt_str
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.document import (
    ContentVisibility,
    Document,
    IngestionStatus,
    SalesContentType,
)
from app.models.query import Query, QueryStatus
from app.models.user import User, UserRole
from sqlalchemy import select

from tests.conftest import register_tenant

_KEY_VERSION = 1


def _doc(tenant_id: uuid.UUID, owner_id: uuid.UUID, name: str) -> Document:
    return Document(
        tenant_id=tenant_id,
        owner_user_id=owner_id,
        filename=name,
        mime_type="text/plain",
        size_bytes=100,
        sha256="0" * 64,
        storage_key=f"k/{name}",
        encryption_key_version=_KEY_VERSION,
        content_type=SalesContentType.PRODUCT,
        visibility=ContentVisibility.REP_VISIBLE,
        status=IngestionStatus.COMPLETED,
        chunk_count=1,
    )


def _query(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    question: str,
    status: QueryStatus,
    confidence: float | None,
    citations: list | None,
) -> Query:
    return Query(
        tenant_id=tenant_id,
        user_id=user_id,
        question_encrypted=encrypt_str(question),
        answer_encrypted=encrypt_str("an answer") if status == QueryStatus.COMPLETED else None,
        citations=citations,
        confidence=confidence,
        status=status,
        encryption_key_version=_KEY_VERSION,
    )


async def _seed(session_factory, tenant_id: uuid.UUID) -> dict:
    """Two reps (one active), a cited + an uncited doc, and four queries by rep1."""
    async with session_factory() as s:
        owner = (
            await s.scalars(
                select(User).where(User.tenant_id == tenant_id, User.role == UserRole.OWNER)
            )
        ).first()
        rep1 = User(
            tenant_id=tenant_id, email="rep1@acme.com",
            hashed_password=hash_password("password-rep111x"),
            role=UserRole.MEMBER, is_active=True,
        )
        rep2 = User(
            tenant_id=tenant_id, email="rep2@acme.com",
            hashed_password=hash_password("password-rep222x"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add_all([rep1, rep2])
        await s.flush()

        cited = _doc(tenant_id, owner.id, "playbook.txt")
        uncited = _doc(tenant_id, owner.id, "unused.txt")
        s.add_all([cited, uncited])
        await s.flush()

        cite = [{"marker": 1, "document_id": str(cited.id),
                 "chunk_id": str(uuid.uuid4()), "filename": cited.filename, "snippet": "x"}]
        s.add_all([
            _query(tenant_id, rep1.id, question="high conf", status=QueryStatus.COMPLETED,
                   confidence=0.9, citations=cite),
            _query(tenant_id, rep1.id, question="low conf coaching question",
                   status=QueryStatus.COMPLETED, confidence=0.3, citations=cite),
            _query(tenant_id, rep1.id, question="held one", status=QueryStatus.PENDING_APPROVAL,
                   confidence=0.4, citations=None),
            _query(tenant_id, rep1.id, question="rejected one", status=QueryStatus.REJECTED,
                   confidence=0.2, citations=None),
        ])
        await s.commit()
        return {"rep1": str(rep1.id), "rep2": str(rep2.id),
                "cited": str(cited.id), "uncited": str(uncited.id)}


async def _member_headers(session_factory, tenant_id: uuid.UUID) -> dict:
    async with session_factory() as s:
        m = User(
            tenant_id=tenant_id, email="ae@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(m)
        await s.commit()
        mid = m.id
    return {"Authorization": f"Bearer {create_access_token(user_id=mid, tenant_id=tenant_id, role='member')}"}


@pytest.mark.asyncio
async def test_overview_aggregates_activity_quality_content(client, acme, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    ids = await _seed(session_factory, tenant_id)
    r = await client.get("/analytics/overview?days=30", headers=acme["headers"])
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_queries"] == 4
    assert body["active_reps"] == 1  # only rep1 asked anything

    reps = {row["email"]: row for row in body["rep_activity"]}
    assert reps["rep1@acme.com"]["query_count"] == 4
    assert reps["rep1@acme.com"]["answered_count"] == 2
    assert reps["rep1@acme.com"]["active"] is True
    assert reps["rep2@acme.com"]["active"] is False  # inactive rep present with 0
    assert reps["rep2@acme.com"]["query_count"] == 0

    q = body["answer_quality"]
    assert q["total"] == 4
    assert q["low_confidence"] == 3  # 0.3, 0.4, 0.2 are all < 0.6
    assert q["pending_approval"] == 1
    assert q["rejected"] == 1
    assert q["with_citations"] == 2
    assert q["citation_coverage_pct"] == 50.0

    ci = body["content_insights"]
    assert any(d["document_id"] == ids["cited"] and d["citation_count"] == 2 for d in ci["most_cited"])
    assert any(d["document_id"] == ids["uncited"] for d in ci["uncited_documents"])

    # Trend is zero-filled and sums to the total; never carries question text.
    assert sum(p["count"] for p in body["query_trend"]) == 4
    assert "question" not in r.text.lower() or "low conf coaching question" not in r.text


@pytest.mark.asyncio
async def test_low_confidence_drilldown_decrypts(client, acme, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    await _seed(session_factory, tenant_id)
    r = await client.get("/analytics/low-confidence?days=30", headers=acme["headers"])
    assert r.status_code == 200, r.text
    items = r.json()
    # Only the COMPLETED + low-confidence query qualifies; its question is decrypted.
    assert len(items) == 1
    assert items[0]["question"] == "low conf coaching question"
    assert items[0]["confidence"] == 0.3
    assert items[0]["user_email"] == "rep1@acme.com"


@pytest.mark.asyncio
async def test_overview_default_view_carries_no_question_text(client, acme, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    await _seed(session_factory, tenant_id)
    r = await client.get("/analytics/overview?days=30", headers=acme["headers"])
    assert "low conf coaching question" not in r.text  # default load never decrypts


@pytest.mark.asyncio
async def test_export_csv(client, acme, session_factory) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    await _seed(session_factory, tenant_id)
    r = await client.get("/analytics/export?days=30", headers=acme["headers"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert "email,role,query_count" in text
    assert "rep1@acme.com" in text


@pytest.mark.asyncio
async def test_analytics_manager_only(client, acme, session_factory) -> None:
    ae = await _member_headers(session_factory, uuid.UUID(acme["tenant_id"]))
    assert (await client.get("/analytics/overview", headers=ae)).status_code == 403
    assert (await client.get("/analytics/low-confidence", headers=ae)).status_code == 403
    assert (await client.get("/analytics/export", headers=ae)).status_code == 403


@pytest.mark.asyncio
async def test_analytics_tenant_isolated(client, acme, session_factory) -> None:
    await _seed(session_factory, uuid.UUID(acme["tenant_id"]))
    other = await register_tenant(client, "globex", "owner@globex.com")
    r = await client.get("/analytics/overview?days=30", headers=other["headers"])
    assert r.status_code == 200
    assert r.json()["total_queries"] == 0  # sees none of acme's data


@pytest.mark.asyncio
async def test_days_param_clamped(client, acme) -> None:
    # ge/le validation rejects out-of-range, but valid extremes must not error.
    assert (await client.get("/analytics/overview?days=1", headers=acme["headers"])).status_code == 200
    assert (await client.get("/analytics/overview?days=365", headers=acme["headers"])).status_code == 200


@pytest.mark.asyncio
async def test_overview_is_audited(client, acme, db_session) -> None:
    await client.get("/analytics/overview", headers=acme["headers"])
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.ANALYTICS_VIEWED in actions
