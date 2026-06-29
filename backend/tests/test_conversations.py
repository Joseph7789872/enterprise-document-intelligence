"""Conversational chat tests: thread scoping, turn threading, history, saved flag."""

from __future__ import annotations

import uuid

import pytest
from app.agents.nodes import WorkflowRunner
from app.core.security import create_access_token, hash_password
from app.models.query import Query
from app.models.user import User, UserRole
from sqlalchemy import select

from tests.conftest import register_tenant


async def _upload(client, headers, name: str, text: str) -> None:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text


async def _second_user_headers(session_factory, tenant_id: uuid.UUID) -> dict:
    async with session_factory() as s:
        user = User(
            tenant_id=tenant_id, email="other@acme.com",
            hashed_password=hash_password("password-secondx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(user)
        await s.commit()
        uid = user.id
    token = create_access_token(user_id=uid, tenant_id=tenant_id, role="member")
    return {"Authorization": f"Bearer {token}"}


# ── Thread CRUD + scoping ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_list_get_conversation(client, acme) -> None:
    h = acme["headers"]
    created = await client.post("/conversations", json={"title": "Pricing chat"}, headers=h)
    assert created.status_code == 201, created.text
    cid = created.json()["id"]

    listed = await client.get("/conversations", headers=h)
    assert [c["id"] for c in listed.json()] == [cid]

    detail = await client.get(f"/conversations/{cid}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["title"] == "Pricing chat"
    assert detail.json()["turns"] == []  # no turns yet


@pytest.mark.asyncio
async def test_conversation_cross_user_and_cross_tenant_404(client, acme, session_factory) -> None:
    cid = (await client.post("/conversations", json={}, headers=acme["headers"])).json()["id"]

    # Another user in the SAME tenant cannot see it.
    other_user = await _second_user_headers(session_factory, uuid.UUID(acme["tenant_id"]))
    assert (await client.get(f"/conversations/{cid}", headers=other_user)).status_code == 404

    # Another tenant cannot see it.
    other_tenant = await register_tenant(client, "globex", "owner@globex.com")
    assert (await client.get(f"/conversations/{cid}", headers=other_tenant["headers"])).status_code == 404


# ── Turn threading ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_turns_thread_into_conversation(client, acme) -> None:
    h = acme["headers"]
    await _upload(client, h, "pricing.txt", "Pro is priced at 110 dollars per seat per month. " * 6)
    cid = (await client.post("/conversations", json={}, headers=h)).json()["id"]

    t1 = await client.post(
        "/query", json={"question": "How is it priced?", "conversation_id": cid}, headers=h
    )
    assert t1.status_code == 200, t1.text
    assert t1.json()["conversation_id"] == cid

    t2 = await client.post(
        "/query", json={"question": "What about for nonprofits?", "conversation_id": cid}, headers=h
    )
    assert t2.json()["conversation_id"] == cid

    # Both turns are in the thread, oldest-first.
    detail = await client.get(f"/conversations/{cid}", headers=h)
    turns = detail.json()["turns"]
    assert [t["question"] for t in turns] == ["How is it priced?", "What about for nonprofits?"]


@pytest.mark.asyncio
async def test_one_shot_query_has_no_conversation(client, acme) -> None:
    await _upload(client, acme["headers"], "p.txt", "Remote work is allowed three days. " * 6)
    r = await client.post("/query", json={"question": "remote work?"}, headers=acme["headers"])
    assert r.status_code == 200
    assert r.json()["conversation_id"] is None


@pytest.mark.asyncio
async def test_invalid_conversation_id_is_404(client, acme) -> None:
    r = await client.post(
        "/query",
        json={"question": "x", "conversation_id": str(uuid.uuid4())},
        headers=acme["headers"],
    )
    assert r.status_code == 404


# ── Streaming threads through too (incl. the human-review branch) ───────────────────────
@pytest.mark.asyncio
async def test_stream_persists_conversation_id(client, acme) -> None:
    h = acme["headers"]
    await _upload(client, h, "p.txt", "Remote work allowed three days. " * 6)
    cid = (await client.post("/conversations", json={}, headers=h)).json()["id"]
    r = await client.post(
        "/query/stream", json={"question": "remote work?", "conversation_id": cid}, headers=h
    )
    assert r.status_code == 200
    assert "event: done" in r.text
    assert cid in r.text  # done payload carries conversation_id

    detail = await client.get(f"/conversations/{cid}", headers=h)
    assert len(detail.json()["turns"]) == 1


@pytest.mark.asyncio
async def test_stream_human_review_branch_threads(client, acme, db_session) -> None:
    # No docs → low confidence → human-review hold; the held turn must keep its thread.
    h = acme["headers"]
    cid = (await client.post("/conversations", json={}, headers=h)).json()["id"]
    r = await client.post(
        "/query/stream", json={"question": "no docs", "conversation_id": cid}, headers=h
    )
    assert "event: pending" in r.text
    assert cid in r.text
    held = (await db_session.scalars(
        select(Query).where(Query.conversation_id == uuid.UUID(cid))
    )).all()
    assert len(held) == 1


# ── History reaches the planner ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_planner_receives_history(client, acme, db_session) -> None:
    """The FakeLLM planner echoes its user message as the sub-query, so prior-turn text
    appearing in the sub-query proves history was injected into the planner prompt."""
    owner = (await db_session.scalars(
        select(User).where(User.tenant_id == uuid.UUID(acme["tenant_id"]))
    )).first()
    runner = WorkflowRunner(db_session, tenant_id=uuid.UUID(acme["tenant_id"]), user_id=owner.id)

    out = await runner.planner(
        {
            "question": "What about for nonprofits?",
            "history": [("How is it priced?", "Pro is 110 dollars/seat [1]")],
        }
    )
    joined = " ".join(out["subqueries"])
    assert "How is it priced?" in joined  # prior question carried into the planner input
    assert "What about for nonprofits?" in joined


@pytest.mark.asyncio
async def test_no_history_keeps_planner_prompt_unchanged(client, acme, db_session) -> None:
    owner = (await db_session.scalars(
        select(User).where(User.tenant_id == uuid.UUID(acme["tenant_id"]))
    )).first()
    runner = WorkflowRunner(db_session, tenant_id=uuid.UUID(acme["tenant_id"]), user_id=owner.id)
    out = await runner.planner({"question": "How much vacation?"})
    assert out["subqueries"] == ["How much vacation?"]  # no history → verbatim


# ── Saved / bookmarked answers ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_save_and_filter_saved_answers(client, acme) -> None:
    h = acme["headers"]
    await _upload(client, h, "p.txt", "Remote work allowed three days. " * 6)
    qid = (await client.post("/query", json={"question": "remote work?"}, headers=h)).json()["query_id"]

    saved = await client.post(f"/query/{qid}/save", headers=h)
    assert saved.status_code == 200
    assert saved.json()["saved"] is True

    only_saved = await client.get("/query?saved_only=true", headers=h)
    assert [q["id"] for q in only_saved.json()] == [qid]

    # Un-saving removes it from the saved view.
    await client.post(f"/query/{qid}/save?saved=false", headers=h)
    assert (await client.get("/query?saved_only=true", headers=h)).json() == []
