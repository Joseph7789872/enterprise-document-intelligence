"""End-to-end ingestion pipeline tests (extract → chunk → embed → store)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from app.core.crypto import decrypt_str, encrypt
from app.models.audit_log import AuditAction, AuditLog
from app.models.document import Document, IngestionStatus
from app.models.document_chunk import DocumentChunk
from app.services.ingestion import process_document
from app.storage import document_storage_key, get_storage
from sqlalchemy import select

FIXTURES = Path(__file__).parent / "fixtures"


async def _seed_document(session_factory, tenant_id, owner_id, data: bytes, filename: str, ct: str):
    """Create a PENDING document with its encrypted bytes in storage."""
    doc_id = uuid.uuid4()
    key = document_storage_key(tenant_id, doc_id)
    get_storage().put(key, encrypt(data).to_token().encode("utf-8"))
    async with session_factory() as s:
        s.add(
            Document(
                id=doc_id,
                tenant_id=tenant_id,
                owner_user_id=owner_id,
                filename=filename,
                content_type=ct,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                storage_key=key,
                encryption_key_version=1,
                status=IngestionStatus.PENDING,
                chunk_count=0,
            )
        )
        await s.commit()
    return doc_id


@pytest.mark.asyncio
async def test_pipeline_completes_and_encrypts_chunks(client, acme, session_factory) -> None:
    # A user must exist as owner; reuse the registered owner via a fresh query.
    from app.models.user import User

    tenant_id = uuid.UUID(acme["tenant_id"])
    async with session_factory() as s:
        owner = (await s.scalars(select(User).where(User.tenant_id == tenant_id))).first()
        owner_id = owner.id

    data = (FIXTURES / "sample.txt").read_bytes()
    doc_id = await _seed_document(session_factory, tenant_id, owner_id, data, "sample.txt", "text/plain")

    await process_document(doc_id)

    async with session_factory() as s:
        doc = await s.get(Document, doc_id)
        assert doc.status == IngestionStatus.COMPLETED
        assert doc.chunk_count > 0
        assert doc.error_message is None

        chunks = list(
            (await s.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))).all()
        )
        assert len(chunks) == doc.chunk_count
        # Chunk text is encrypted at rest but decrypts back to real content.
        plaintext = data.decode()
        for c in chunks:
            assert c.content_encrypted != ""
            assert "Acme" not in c.content_encrypted  # not stored in the clear
            decrypted = decrypt_str(c.content_encrypted)
            assert decrypted and decrypted in plaintext
            assert len(c.embedding) == 3072
            assert c.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_pipeline_marks_failed_on_unsupported_type(client, acme, session_factory) -> None:
    from app.models.user import User

    tenant_id = uuid.UUID(acme["tenant_id"])
    async with session_factory() as s:
        owner = (await s.scalars(select(User).where(User.tenant_id == tenant_id))).first()
        owner_id = owner.id

    # Bytes that extraction cannot handle (svg content type).
    doc_id = await _seed_document(
        session_factory, tenant_id, owner_id, b"<svg/>", "drawing.svg", "image/svg+xml"
    )

    await process_document(doc_id)

    async with session_factory() as s:
        doc = await s.get(Document, doc_id)
        assert doc.status == IngestionStatus.FAILED
        assert doc.error_message
        failures = list(
            (
                await s.scalars(
                    select(AuditLog).where(AuditLog.action == AuditAction.DOCUMENT_INGESTION_FAILED)
                )
            ).all()
        )
        assert len(failures) == 1
