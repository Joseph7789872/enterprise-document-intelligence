"""Bulk upload tests: partial failure, ingestion, auth, isolation."""

from __future__ import annotations

import pytest
from app.models.document import IngestionStatus

from tests.conftest import register_tenant


def _file(name: str, text: str) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, text.encode("utf-8"), "text/plain"))


@pytest.mark.asyncio
async def test_batch_all_valid_accepted_and_ingested(client, acme) -> None:
    files = [
        _file("a.txt", "Acme pricing is simple. " * 6),
        _file("b.txt", "Our ICP is mid-market SaaS. " * 6),
        _file("c.txt", "We win on security. " * 6),
    ]
    r = await client.post("/documents/batch", files=files, headers=acme["headers"])
    assert r.status_code == 207, r.text
    results = r.json()["results"]
    assert len(results) == 3
    assert all(item["status"] == "accepted" for item in results)
    # Background ingestion completes before the response settles → each is COMPLETED.
    for item in results:
        got = await client.get(f"/documents/{item['id']}", headers=acme["headers"])
        assert got.status_code == 200
        assert got.json()["status"] == IngestionStatus.COMPLETED.value
        assert got.json()["chunk_count"] > 0


@pytest.mark.asyncio
async def test_batch_partial_failure_does_not_500(client, acme) -> None:
    files = [
        _file("good1.txt", "Valid content here. " * 6),
        ("files", ("bad.exe", b"MZ\x00binary", "application/octet-stream")),
        _file("good2.txt", "More valid content. " * 6),
    ]
    r = await client.post("/documents/batch", files=files, headers=acme["headers"])
    assert r.status_code == 207, r.text
    results = {item["filename"]: item for item in r.json()["results"]}
    assert results["good1.txt"]["status"] == "accepted"
    assert results["good2.txt"]["status"] == "accepted"
    assert results["bad.exe"]["status"] == "rejected"
    assert results["bad.exe"]["error"] == "unsupported_type"


@pytest.mark.asyncio
async def test_batch_empty_file_rejected(client, acme) -> None:
    files = [_file("ok.txt", "Content. " * 6), ("files", ("empty.txt", b"", "text/plain"))]
    r = await client.post("/documents/batch", files=files, headers=acme["headers"])
    assert r.status_code == 207
    results = {item["filename"]: item for item in r.json()["results"]}
    assert results["empty.txt"]["status"] == "rejected"
    assert results["empty.txt"]["error"] == "empty"


@pytest.mark.asyncio
async def test_batch_requires_auth(client) -> None:
    r = await client.post("/documents/batch", files=[_file("a.txt", "x " * 6)])
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_batch_is_tenant_scoped(client, acme) -> None:
    r = await client.post(
        "/documents/batch", files=[_file("acme.txt", "Acme secret sauce. " * 6)],
        headers=acme["headers"],
    )
    doc_id = r.json()["results"][0]["id"]
    other = await register_tenant(client, "globex", "owner@globex.com")
    cross = await client.get(f"/documents/{doc_id}", headers=other["headers"])
    assert cross.status_code == 404
