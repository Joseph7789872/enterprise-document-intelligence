"""Document ingestion pipeline.

``process_document`` runs the full extract → chunk → embed → store flow for a single
document and tracks status on the ``documents`` row. It is invoked as a FastAPI
``BackgroundTask`` after the upload response is returned. The function owns its own DB
session (the request's session is already closed by then) and is structured so it can
be moved behind a Celery task later without changing the pipeline body.

Security: bytes are decrypted from storage only in memory; each chunk's text is
re-encrypted (``encrypt_str``) before being written to ``document_chunks``.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select

from app.core.config import settings
from app.core.crypto import decrypt, encrypt_str
from app.db import session as db_session
from app.models.audit_log import AuditAction
from app.models.document import Document, IngestionStatus
from app.models.document_chunk import DocumentChunk
from app.services import audit_service, chunking, extraction
from app.services.embeddings import get_embedder
from app.storage import get_storage

logger = logging.getLogger(__name__)


async def process_document(document_id: uuid.UUID, trace_id: str | None = None) -> None:
    """Ingest a single document. Never raises — failures are recorded on the row."""
    async with db_session.SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning("process_document: document %s not found", document_id)
            return

        document.status = IngestionStatus.PROCESSING
        await session.commit()

        try:
            await _run_pipeline(session, document)
            document.status = IngestionStatus.COMPLETED
            document.error_message = None
            await session.flush()
            await audit_service.write_event(
                session,
                tenant_id=document.tenant_id,
                action=AuditAction.DOCUMENT_INGESTED,
                actor_user_id=document.owner_user_id,
                resource_type="document",
                resource_id=str(document.id),
                metadata={"chunk_count": document.chunk_count, "page_count": document.page_count},
                trace_id=trace_id,
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - pipeline must never crash the worker
            await session.rollback()
            logger.exception("Ingestion failed for document %s", document_id)
            await _mark_failed(document_id, str(exc), trace_id)


async def _run_pipeline(session, document: Document) -> None:  # type: ignore[no-untyped-def]
    storage = get_storage()
    embedder = get_embedder()

    # 1. Load + decrypt the original bytes.
    encrypted = storage.get(document.storage_key)
    plaintext = decrypt(_blob_from_stored(encrypted))

    # 2. Extract text.
    extracted = extraction.extract_text(plaintext, document.mime_type, document.filename)
    document.page_count = extracted.page_count

    # 3. Chunk.
    chunks = chunking.split(extracted.text)
    if not chunks:
        raise extraction.ExtractionError("No chunks produced from document text.")

    # 4. Embed (batched inside the embedder).
    embeddings = await embedder.embed_texts([c.text for c in chunks])

    # On PostgreSQL, derive the FTS vector server-side from the plaintext so only
    # stemmed lexemes are persisted (the full text stays encrypted). On SQLite this
    # is left NULL and keyword search uses the in-process fallback.
    is_pg = session.bind is not None and session.bind.dialect.name == "postgresql"

    # 5. Encrypt chunk text + persist.
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        session.add(
            DocumentChunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                chunk_index=chunk.metadata["chunk_index"],
                content_encrypted=encrypt_str(chunk.text),
                token_count=chunk.token_count,
                embedding=embedding,
                chunk_metadata=chunk.metadata,
                encryption_key_version=settings.ENCRYPTION_KEY_VERSION,
                content_tsv=(
                    func.to_tsvector(settings.FTS_LANGUAGE, chunk.text) if is_pg else None
                ),
            )
        )
    document.chunk_count = len(chunks)
    await session.flush()


async def _mark_failed(document_id: uuid.UUID, message: str, trace_id: str | None) -> None:
    """Record FAILED status + audit in a fresh transaction (the prior one rolled back)."""
    async with db_session.SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:  # pragma: no cover - defensive
            return
        document.status = IngestionStatus.FAILED
        document.error_message = message[:2000]
        await session.flush()
        await audit_service.write_event(
            session,
            tenant_id=document.tenant_id,
            action=AuditAction.DOCUMENT_INGESTION_FAILED,
            actor_user_id=document.owner_user_id,
            resource_type="document",
            resource_id=str(document.id),
            metadata={"error": message[:500]},
            trace_id=trace_id,
        )
        await session.commit()


def _blob_from_stored(data: bytes):  # type: ignore[no-untyped-def]
    """Decode stored bytes back into an EncryptedBlob.

    Storage holds the base64 token produced by ``EncryptedBlob.to_token`` (see the
    upload path), so we reconstruct the blob from it.
    """
    from app.core.crypto import EncryptedBlob

    return EncryptedBlob.from_token(data.decode("utf-8"))


async def _find_pending(session) -> list[Document]:  # type: ignore[no-untyped-def] # pragma: no cover
    """Helper for future requeue tooling: list documents stuck PENDING."""
    result = await session.scalars(
        select(Document).where(Document.status == IngestionStatus.PENDING)
    )
    return list(result.all())
