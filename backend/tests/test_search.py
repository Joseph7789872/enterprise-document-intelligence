"""Hybrid search endpoint tests: relevance, provenance, isolation, audit of access."""

from __future__ import annotations

import pytest
from app.models.audit_log import AuditAction, AuditLog
from sqlalchemy import select

from tests.conftest import register_tenant


async def _upload_text(client, headers, name: str, text: str) -> str:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_search_returns_relevant_chunks(client, acme) -> None:
    await _upload_text(
        client, acme["headers"], "vacation.txt",
        "Employees receive twenty days of paid vacation leave each year. " * 8,
    )
    await _upload_text(
        client, acme["headers"], "security.txt",
        "All confidential client data must be encrypted at rest and in transit. " * 8,
    )

    r = await client.post(
        "/search", json={"query": "how much vacation do employees get", "top_k": 5},
        headers=acme["headers"],
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) >= 1
    # Scores are sorted descending and snippets are decrypted (human-readable).
    scores = [x["score"] for x in results]
    assert scores == sorted(scores, reverse=True)
    assert any("vacation" in x["snippet"].lower() for x in results)
    # Each result carries retrieval-method provenance, and none are duplicated.
    assert all(x["methods"] for x in results)
    chunk_ids = [x["chunk_id"] for x in results]
    assert len(chunk_ids) == len(set(chunk_ids))


@pytest.mark.asyncio
async def test_search_audit_records_method_breakdown(client, acme, db_session) -> None:
    await _upload_text(
        client, acme["headers"], "policy.txt",
        "Remote work is permitted up to three days per week. " * 8,
    )
    await client.post(
        "/search", json={"query": "remote work", "top_k": 5}, headers=acme["headers"]
    )
    event = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.SEARCH_PERFORMED)
        )
    ).first()
    assert event is not None
    assert event.event_metadata["reranker"] == "fake"
    assert event.event_metadata["bm25_enabled"] is True


@pytest.mark.asyncio
async def test_search_is_tenant_isolated(client, acme) -> None:
    await _upload_text(
        client, acme["headers"], "secret.txt",
        "Acme internal merger plans are strictly confidential. " * 8,
    )
    other = await register_tenant(client, "globex", "owner@globex.com")

    # Globex has no documents → no results, and never sees Acme's chunks.
    r = await client.post(
        "/search", json={"query": "merger plans", "top_k": 5}, headers=other["headers"]
    )
    assert r.status_code == 200
    assert r.json()["results"] == []


@pytest.mark.asyncio
async def test_search_records_accessed_ids(client, acme, db_session) -> None:
    doc_id = await _upload_text(
        client, acme["headers"], "policy.txt",
        "Remote work is permitted up to three days per week. " * 8,
    )
    r = await client.post(
        "/search", json={"query": "remote work policy", "top_k": 3}, headers=acme["headers"]
    )
    assert r.status_code == 200

    event = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.SEARCH_PERFORMED)
        )
    ).first()
    assert event is not None
    assert doc_id in event.event_metadata["document_ids"]
    assert len(event.event_metadata["chunk_ids"]) == len(event.event_metadata["document_ids"])


@pytest.mark.asyncio
async def test_search_requires_auth(client) -> None:
    r = await client.post("/search", json={"query": "anything", "top_k": 3})
    assert r.status_code == 401
