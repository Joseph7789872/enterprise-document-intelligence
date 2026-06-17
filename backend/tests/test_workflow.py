"""End-to-end workflow graph tests (FakeLLM)."""

from __future__ import annotations

import uuid

import pytest
from app.agents.nodes import WorkflowRunner
from app.agents.state import QueryState
from app.agents.workflow import build_workflow
from app.models.user import User
from sqlalchemy import select


async def _upload(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text


async def _runner(db_session, tenant_id: uuid.UUID) -> WorkflowRunner:
    owner = (await db_session.scalars(select(User).where(User.tenant_id == tenant_id))).first()
    return WorkflowRunner(db_session, tenant_id=tenant_id, user_id=owner.id)


@pytest.mark.asyncio
async def test_workflow_answers_with_citations(client, acme, db_session) -> None:
    await _upload(
        client, acme["headers"], "policy.txt",
        "Remote work is permitted up to three days per week. " * 6,
    )
    tenant_id = uuid.UUID(acme["tenant_id"])
    runner = await _runner(db_session, tenant_id)
    graph = build_workflow(runner)

    state = await graph.ainvoke(
        {"question": "What is the remote work policy?", "tenant_id": tenant_id, "user_id": runner.user_id}
    )
    assert state["status"] == QueryState.COMPLETED
    assert state["answer"]
    assert state["citations"]  # [1] marker mapped to a real chunk
    assert state["citations"][0].document_id is not None


@pytest.mark.asyncio
async def test_workflow_holds_low_confidence_for_review(client, acme, db_session) -> None:
    await _upload(client, acme["headers"], "policy.txt", "Remote work policy details. " * 6)
    tenant_id = uuid.UUID(acme["tenant_id"])
    runner = await _runner(db_session, tenant_id)
    graph = build_workflow(runner)

    # The [lowconf] marker forces the FakeLLM verifier to return low confidence.
    state = await graph.ainvoke(
        {"question": "[lowconf] remote work?", "tenant_id": tenant_id, "user_id": runner.user_id}
    )
    assert state["status"] == QueryState.PENDING_APPROVAL
    assert state.get("requires_approval") is True
    assert "answer" not in state  # no autonomous answer delivered


@pytest.mark.asyncio
async def test_workflow_holds_when_no_sources(client, acme, db_session) -> None:
    # Tenant with no documents → empty retrieval → low confidence → review.
    tenant_id = uuid.UUID(acme["tenant_id"])
    runner = await _runner(db_session, tenant_id)
    graph = build_workflow(runner)
    state = await graph.ainvoke(
        {"question": "anything at all", "tenant_id": tenant_id, "user_id": runner.user_id}
    )
    assert state["status"] == QueryState.PENDING_APPROVAL
