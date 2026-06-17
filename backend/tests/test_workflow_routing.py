"""Workflow-level routing tests (Phase 7): confidential docs → self-hosted; fail-closed."""

from __future__ import annotations

import uuid

import pytest
from app.agents.nodes import WorkflowRunner
from app.agents.workflow import build_workflow
from app.errors import LLMRoutingError
from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User
from app.services.llm import FakeLLM
from app.services.model_router import ModelRouter
from sqlalchemy import select


async def _upload_confidential(client, headers, text: str) -> None:
    files = {"file": ("privileged.txt", text.encode("utf-8"), "text/plain")}
    r = await client.post(
        "/documents", files=files, data={"classification_level": "confidential"}, headers=headers
    )
    assert r.status_code == 202, r.text


async def _owner_id(db_session, tenant_id: uuid.UUID) -> uuid.UUID:
    owner = (await db_session.scalars(select(User).where(User.tenant_id == tenant_id))).first()
    return owner.id


@pytest.mark.asyncio
async def test_confidential_routes_to_self_hosted_profile(client, acme, db_session) -> None:
    await _upload_confidential(client, acme["headers"], "Privileged client matter notes. " * 6)
    tenant_id = uuid.UUID(acme["tenant_id"])
    user_id = await _owner_id(db_session, tenant_id)

    # A router with BOTH profiles wired to deterministic fakes.
    router = ModelRouter(cloud=FakeLLM(), self_hosted=FakeLLM())
    runner = WorkflowRunner(
        db_session, tenant_id=tenant_id, user_id=user_id, router=router
    )
    state = await build_workflow(runner).ainvoke(
        {"question": "What do the notes say?", "tenant_id": tenant_id, "user_id": user_id}
    )
    assert state["max_classification"].value == "confidential"

    # The synthesizer's LLM_CALL must record the self_hosted profile.
    rows = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.LLM_CALL)
        )
    ).all()
    synth = [r for r in rows if (r.event_metadata or {}).get("node") == "synthesizer"]
    assert synth and synth[-1].event_metadata["profile"] == "self_hosted"


@pytest.mark.asyncio
async def test_fail_closed_when_no_self_hosted_profile(client, acme, db_session) -> None:
    await _upload_confidential(client, acme["headers"], "Confidential figures. " * 6)
    tenant_id = uuid.UUID(acme["tenant_id"])
    user_id = await _owner_id(db_session, tenant_id)

    # Self-hosted profile is absent → sensitive routing must fail closed, not hit cloud.
    router = ModelRouter(cloud=FakeLLM(), self_hosted=None)
    runner = WorkflowRunner(
        db_session, tenant_id=tenant_id, user_id=user_id, router=router
    )
    with pytest.raises(LLMRoutingError):
        await build_workflow(runner).ainvoke(
            {"question": "What are the figures?", "tenant_id": tenant_id, "user_id": user_id}
        )


@pytest.mark.asyncio
async def test_query_endpoint_returns_503_and_audits_denial(client, acme, db_session) -> None:
    # The default router (no LLM_BASE_URL in the test env) has no self-hosted profile, so a
    # confidential query fails closed end-to-end through the /query endpoint.
    await _upload_confidential(client, acme["headers"], "Highly confidential text. " * 6)
    r = await client.post("/query", json={"question": "summarize it"}, headers=acme["headers"])
    assert r.status_code == 503, r.text

    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.LLM_ROUTE_DENIED in actions
