"""Notion connector tests: encrypted token storage, status, sync, gating."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from app.core.crypto import decrypt_str
from app.core.security import create_access_token, hash_password
from app.models.connector_credential import ConnectorCredential, ConnectorProvider
from app.models.document import IngestionStatus
from app.models.user import User, UserRole
from app.services.connectors import notion
from app.services.connectors.notion import FakeNotionClient, NotionPage
from sqlalchemy import select

_TOKEN = "secret_ntn_super_secret_value_123"  # noqa: S105 - test fixture, not a real secret


@pytest.fixture
def fake_notion() -> Iterator[None]:
    notion.set_notion_client(
        FakeNotionClient(
            [
                NotionPage(id="p1", title="Pricing", text="Pro is $110 per seat per month. " * 4),
                NotionPage(id="p2", title="ICP", text="We sell to mid-market SaaS teams. " * 4),
            ]
        )
    )
    yield
    notion.set_notion_client(None)


async def _member_headers(session_factory, tenant_id: uuid.UUID) -> dict:
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="ae@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        mid = member.id
    return {"Authorization": f"Bearer {create_access_token(user_id=mid, tenant_id=tenant_id, role='member')}"}


@pytest.mark.asyncio
async def test_set_token_then_status_never_leaks_token(client, acme, db_session) -> None:
    h = acme["headers"]
    put = await client.put("/connectors/notion/token", json={"token": _TOKEN}, headers=h)
    assert put.status_code == 200, put.text
    assert _TOKEN not in put.text  # token never echoed

    status = await client.get("/connectors/notion", headers=h)
    assert status.status_code == 200
    assert status.json()["connected"] is True
    assert _TOKEN not in status.text

    # Stored encrypted; decrypts back to the original.
    cred = (
        await db_session.scalars(
            select(ConnectorCredential).where(
                ConnectorCredential.tenant_id == uuid.UUID(acme["tenant_id"]),
                ConnectorCredential.provider == ConnectorProvider.NOTION,
            )
        )
    ).first()
    assert cred is not None
    assert cred.token_encrypted != _TOKEN  # ciphertext
    assert decrypt_str(cred.token_encrypted) == _TOKEN


@pytest.mark.asyncio
async def test_status_when_not_connected(client, acme) -> None:
    r = await client.get("/connectors/notion", headers=acme["headers"])
    assert r.status_code == 200
    assert r.json()["connected"] is False


@pytest.mark.asyncio
async def test_sync_ingests_pages(client, acme, fake_notion) -> None:
    h = acme["headers"]
    await client.put("/connectors/notion/token", json={"token": _TOKEN}, headers=h)
    sync = await client.post("/connectors/notion/sync", headers=h)
    assert sync.status_code == 200, sync.text
    results = sync.json()["results"]
    assert {r["filename"] for r in results} == {"Pricing", "ICP"}
    assert all(r["status"] == "accepted" for r in results)
    # Each Notion page became a COMPLETED document.
    for r in results:
        got = await client.get(f"/documents/{r['id']}", headers=h)
        assert got.json()["status"] == IngestionStatus.COMPLETED.value
        assert got.json()["chunk_count"] > 0

    # last_synced_at is now set.
    status = await client.get("/connectors/notion", headers=h)
    assert status.json()["last_synced_at"] is not None


@pytest.mark.asyncio
async def test_sync_without_token_404(client, acme, fake_notion) -> None:
    r = await client.post("/connectors/notion/sync", headers=acme["headers"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_connector_manager_only(client, acme, session_factory) -> None:
    ae = await _member_headers(session_factory, uuid.UUID(acme["tenant_id"]))
    assert (await client.put("/connectors/notion/token", json={"token": _TOKEN}, headers=ae)).status_code == 403
    assert (await client.get("/connectors/notion", headers=ae)).status_code == 403
    assert (await client.post("/connectors/notion/sync", headers=ae)).status_code == 403


@pytest.mark.asyncio
async def test_token_is_tenant_scoped(client, acme, fake_notion) -> None:
    from tests.conftest import register_tenant

    await client.put("/connectors/notion/token", json={"token": _TOKEN}, headers=acme["headers"])
    other = await register_tenant(client, "globex", "owner@globex.com")
    # Globex has no token of its own.
    assert (await client.get("/connectors/notion", headers=other["headers"])).json()["connected"] is False
