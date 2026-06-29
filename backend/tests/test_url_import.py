"""URL import tests: fake fetcher → HTML extraction → ingestion; failures; gating."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.core.config import settings
from app.models.document import IngestionStatus
from app.services import fetcher
from app.services.fetcher import FetchError, FetchResult


class _StubFetcher:
    """Returns canned HTML for any URL (or raises if constructed with an error)."""

    def __init__(self, result: FetchResult | None = None, error: str | None = None) -> None:
        self._result = result
        self._error = error

    async def fetch(self, url: str) -> FetchResult:
        if self._error is not None:
            raise FetchError(self._error)
        assert self._result is not None
        return self._result


@pytest.fixture
def stub_fetcher() -> Iterator[None]:
    """Install a fetcher per-test, cleared afterwards."""
    yield
    fetcher.set_fetcher(None)


_HTML = b"<html><body><h1>Veloxa Pricing</h1><p>Pro is $110 per seat.</p></body></html>"


@pytest.mark.asyncio
async def test_url_import_ingests_html(client, acme, stub_fetcher) -> None:
    fetcher.set_fetcher(
        _StubFetcher(
            FetchResult(
                url="https://veloxa.example.com/pricing",
                final_url="https://veloxa.example.com/pricing",
                content=_HTML,
                content_type="text/html",
            )
        )
    )
    r = await client.post(
        "/documents/import-url",
        json={"url": "https://veloxa.example.com/pricing"},
        headers=acme["headers"],
    )
    assert r.status_code == 202, r.text
    doc_id = r.json()["id"]
    # End-to-end: HTML was extracted, chunked, embedded.
    got = await client.get(f"/documents/{doc_id}", headers=acme["headers"])
    assert got.status_code == 200
    assert got.json()["status"] == IngestionStatus.COMPLETED.value
    assert got.json()["chunk_count"] > 0
    assert got.json()["mime_type"] == "text/html"


@pytest.mark.asyncio
async def test_url_import_fetch_failure_is_4xx(client, acme, stub_fetcher) -> None:
    fetcher.set_fetcher(_StubFetcher(error="boom"))
    r = await client.post(
        "/documents/import-url", json={"url": "https://nope.example.com"}, headers=acme["headers"]
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_url_import_manager_only(client, acme, session_factory, stub_fetcher) -> None:
    import uuid

    from app.core.security import create_access_token, hash_password
    from app.models.user import User, UserRole

    tenant_id = uuid.UUID(acme["tenant_id"])
    async with session_factory() as s:
        member = User(
            tenant_id=tenant_id, email="ae@acme.com",
            hashed_password=hash_password("password-memberx"),
            role=UserRole.MEMBER, is_active=True,
        )
        s.add(member)
        await s.commit()
        mid = member.id
    ae = {"Authorization": f"Bearer {create_access_token(user_id=mid, tenant_id=tenant_id, role='member')}"}
    fetcher.set_fetcher(_StubFetcher(error="unused"))
    r = await client.post(
        "/documents/import-url", json={"url": "https://x.example.com"}, headers=ae
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_url_import_404_when_flag_off(client, acme, monkeypatch, stub_fetcher) -> None:
    monkeypatch.setattr(settings, "ENABLE_CONNECTORS", False)
    fetcher.set_fetcher(_StubFetcher(error="unused"))
    r = await client.post(
        "/documents/import-url", json={"url": "https://x.example.com"}, headers=acme["headers"]
    )
    assert r.status_code == 404
