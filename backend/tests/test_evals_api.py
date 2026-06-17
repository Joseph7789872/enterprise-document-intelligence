"""Eval dashboard API tests: role-gating, tenant isolation, audit."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.eval_run import EvalRun
from app.models.user import User, UserRole
from app.services.eval_harness import GroundTruthDataset, GroundTruthItem, run_eval
from app.services.evaluation import FakeEvaluator
from sqlalchemy import select

from tests.conftest import register_tenant


async def _upload(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text


async def _owner_id(db_session, tenant_id: uuid.UUID) -> uuid.UUID:
    owner = (
        await db_session.scalars(select(User).where(User.tenant_id == tenant_id))
    ).first()
    return owner.id


async def _make_run(client, db_session, acme) -> EvalRun:
    """Create a committed eval run owned by the acme tenant."""
    await _upload(
        client, acme["headers"], "policy.txt",
        "Employees accrue twenty days of paid vacation leave each year. " * 4,
    )
    tenant_id = uuid.UUID(acme["tenant_id"])
    owner_id = await _owner_id(db_session, tenant_id)
    dataset = GroundTruthDataset(
        name="api_probe",
        items=[
            GroundTruthItem(
                id="vac-01",
                question="How many vacation days do employees accrue each year?",
                ground_truth="Employees accrue twenty days of paid vacation leave each year.",
            )
        ],
    )
    run = await run_eval(
        db_session, tenant_id=tenant_id, user_id=owner_id,
        dataset=dataset, evaluator=FakeEvaluator(),
    )
    await db_session.commit()
    return run


@pytest.mark.asyncio
async def test_list_and_get_eval_runs(client, acme, db_session) -> None:
    run = await _make_run(client, db_session, acme)

    listed = await client.get("/evals/runs", headers=acme["headers"])
    assert listed.status_code == 200, listed.text
    ids = [r["id"] for r in listed.json()]
    assert str(run.id) in ids

    detail = await client.get(f"/evals/runs/{run.id}", headers=acme["headers"])
    assert detail.status_code == 200
    body = detail.json()
    assert body["dataset_name"] == "api_probe"
    assert body["results"] and body["results"][0]["item_id"] == "vac-01"


@pytest.mark.asyncio
async def test_eval_runs_require_admin(client, acme, db_session, session_factory) -> None:
    await _make_run(client, db_session, acme)
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
    resp = await client.get("/evals/runs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_eval_run_is_tenant_isolated(client, acme, db_session) -> None:
    run = await _make_run(client, db_session, acme)
    other = await register_tenant(client, "globex", "owner@globex.com")
    cross = await client.get(f"/evals/runs/{run.id}", headers=other["headers"])
    assert cross.status_code == 404


@pytest.mark.asyncio
async def test_eval_view_is_audited(client, acme, db_session) -> None:
    run = await _make_run(client, db_session, acme)
    await client.get(f"/evals/runs/{run.id}", headers=acme["headers"])
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.EVAL_RESULTS_VIEWED in actions
    assert AuditAction.EVAL_RUN_STARTED in actions
    assert AuditAction.EVAL_RUN_COMPLETED in actions
