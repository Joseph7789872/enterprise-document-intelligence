"""Documents API tests: upload, validation gates, tenant isolation."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.models.audit_log import AuditAction, AuditLog
from app.models.document import IngestionStatus
from app.models.document_chunk import DocumentChunk
from sqlalchemy import func, select

from tests.conftest import register_tenant

FIXTURES = Path(__file__).parent / "fixtures"
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _txt_upload(name: str = "sample.txt", content: bytes | None = None):
    data = content if content is not None else (FIXTURES / "sample.txt").read_bytes()
    return {"file": (name, data, "text/plain")}


@pytest.mark.asyncio
async def test_upload_accepts_and_ingests(client, acme) -> None:
    r = await client.post("/documents", files=_txt_upload(), headers=acme["headers"])
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == IngestionStatus.PENDING.value
    doc_id = body["id"]

    # Background ingestion runs before the ASGI response settles → COMPLETED.
    got = await client.get(f"/documents/{doc_id}", headers=acme["headers"])
    assert got.status_code == 200
    assert got.json()["status"] == IngestionStatus.COMPLETED.value
    assert got.json()["chunk_count"] > 0


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(client, acme) -> None:
    files = {"file": ("evil.exe", b"MZ...", "application/octet-stream")}
    r = await client.post("/documents", files=files, headers=acme["headers"])
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_oversize(client, acme, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1, raising=False)  # 1 MB cap
    big = b"x" * (2 * 1024 * 1024)  # 2 MB, over the cap
    r = await client.post("/documents", files=_txt_upload(content=big), headers=acme["headers"])
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_upload_rejects_malware(client, acme) -> None:
    r = await client.post(
        "/documents", files=_txt_upload(content=EICAR), headers=acme["headers"]
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_upload_requires_auth(client) -> None:
    r = await client.post("/documents", files=_txt_upload())
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_documents_are_tenant_isolated(client, acme, db_session) -> None:
    # Acme uploads a document.
    up = await client.post("/documents", files=_txt_upload(), headers=acme["headers"])
    doc_id = up.json()["id"]

    # A second tenant cannot see it (404, not 403 — no existence leak).
    other = await register_tenant(client, "globex", "owner@globex.com")
    cross = await client.get(f"/documents/{doc_id}", headers=other["headers"])
    assert cross.status_code == 404

    # And its own listing is empty.
    listing = await client.get("/documents", headers=other["headers"])
    assert listing.status_code == 200
    assert listing.json() == []


@pytest.mark.asyncio
async def test_delete_purges_chunks_so_content_is_not_retrievable(
    client, acme, db_session
) -> None:
    """Regression: soft-deleting a document must purge its chunks/embeddings.

    Managers retrieve with an unrestricted document filter, so leaving chunks
    behind let deleted content keep being cited in answers (BUG-1).
    """
    up = await client.post("/documents", files=_txt_upload(), headers=acme["headers"])
    doc_id = up.json()["id"]

    async def chunk_count() -> int:
        return await db_session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
        )

    assert await chunk_count() > 0, "document should have chunks after ingestion"

    deleted = await client.delete(f"/documents/{doc_id}", headers=acme["headers"])
    assert deleted.status_code == 204, deleted.text

    # Document is soft-deleted (404) and its chunks/embeddings are gone.
    got = await client.get(f"/documents/{doc_id}", headers=acme["headers"])
    assert got.status_code == 404
    assert await chunk_count() == 0, "chunks must be purged on delete"


@pytest.mark.asyncio
async def test_upload_is_audited(client, acme, db_session) -> None:
    await client.post("/documents", files=_txt_upload(), headers=acme["headers"])
    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.DOCUMENT_UPLOADED in actions
    assert AuditAction.DOCUMENT_INGESTED in actions
