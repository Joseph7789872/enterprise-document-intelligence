"""Agent node tests (planner, retriever, verifier, routing)."""

from __future__ import annotations

import uuid

import pytest
from app.agents.nodes import WorkflowRunner, route_after_verify
from app.agents.state import Verification
from app.models.user import User
from sqlalchemy import select


async def _upload(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text


async def _runner_for(db_session, tenant_id: uuid.UUID) -> WorkflowRunner:
    owner = (await db_session.scalars(select(User).where(User.tenant_id == tenant_id))).first()
    return WorkflowRunner(db_session, tenant_id=tenant_id, user_id=owner.id)


@pytest.mark.asyncio
async def test_planner_returns_subqueries(client, acme, db_session) -> None:
    runner = await _runner_for(db_session, uuid.UUID(acme["tenant_id"]))
    out = await runner.planner({"question": "How much vacation do employees get?"})
    assert out["subqueries"] == ["How much vacation do employees get?"]


@pytest.mark.asyncio
async def test_retriever_is_tenant_scoped_and_decrypts(client, acme, db_session) -> None:
    await _upload(
        client, acme["headers"], "vacation.txt",
        "Employees receive twenty days of paid vacation leave each year. " * 6,
    )
    tenant_id = uuid.UUID(acme["tenant_id"])
    runner = await _runner_for(db_session, tenant_id)
    out = await runner.retriever({"subqueries": ["vacation leave"]})
    chunks = out["chunks"]
    assert chunks
    assert any("vacation" in c.text.lower() for c in chunks)  # decrypted text


@pytest.mark.asyncio
async def test_retriever_empty_for_other_tenant(client, acme, db_session) -> None:
    await _upload(client, acme["headers"], "secret.txt", "Confidential merger plans. " * 6)
    runner = WorkflowRunner(db_session, tenant_id=uuid.uuid4(), user_id=uuid.uuid4())
    out = await runner.retriever({"subqueries": ["merger plans"]})
    assert out["chunks"] == []


@pytest.mark.asyncio
async def test_verifier_low_confidence_without_sources(client, acme, db_session) -> None:
    runner = await _runner_for(db_session, uuid.UUID(acme["tenant_id"]))
    out = await runner.verifier({"question": "anything", "chunks": []})
    assert out["verification"].confidence == 0.0
    assert not out["verification"].is_grounded


def test_route_after_verify_branches() -> None:
    high = {"verification": Verification(confidence=0.9, is_grounded=True)}
    low = {"verification": Verification(confidence=0.2, is_grounded=False)}
    flagged = {"verification": Verification(confidence=0.9, is_grounded=True, confidentiality_concern=True)}
    assert route_after_verify(high) == "synthesizer"
    assert route_after_verify(low) == "human_review"
    assert route_after_verify(flagged) == "human_review"
