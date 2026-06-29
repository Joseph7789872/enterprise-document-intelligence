"""Shared document intake — the common path every content source funnels through.

Single upload, bulk upload, URL import, and the Notion connector all call
:func:`intake_document`: malware-scan → hash → envelope-encrypt → store → create the
``Document`` row (PENDING) → apply segment tags → audit → queue the background ingestion
pipeline. It deliberately does NOT enforce the user-upload extension allowlist or size
cap (those belong to the HTTP layer) and does NOT commit (it shares the caller's
transaction, like the audit service) — the caller commits before returning so the
background ``process_document`` (which opens its own session) sees a committed row.
"""

from __future__ import annotations

import hashlib
import uuid

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt
from app.models.audit_log import AuditAction
from app.models.document import ContentVisibility, Document, IngestionStatus, SalesContentType
from app.services import audit_service, billing_service, malware_scan, segment_service
from app.services.ingestion import process_document
from app.storage import document_storage_key, get_storage


class IntakeError(Exception):
    """A per-source validation failure (empty / malware). Callers map it to an HTTP error
    (single upload) or a per-item ``rejected`` result (bulk)."""

    def __init__(self, reason: str, signature: str | None = None) -> None:
        self.reason = reason
        self.signature = signature
        super().__init__(reason)


async def intake_document(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    filename: str,
    mime_type: str,
    data: bytes,
    content_type: SalesContentType,
    visibility: ContentVisibility,
    segment_ids: list[uuid.UUID],
    background: BackgroundTasks,
    trace_id: str | None,
    source: str = "upload",
    ip_address: str | None = None,
) -> Document:
    """Store ``data`` encrypted, create its Document row, and queue ingestion.

    Raises :class:`IntakeError` (before any storage/DB write) for empty or malware input.
    """
    if not data:
        raise IntakeError("empty")
    scan = malware_scan.scan(data)
    if not scan.clean:
        raise IntakeError("malware", scan.signature)

    # Plan-limit gate (no-op unless ENABLE_BILLING): blocks once the tenant hits its
    # document cap. Covers every source — single/bulk upload, URL import, Notion sync —
    # since all of them funnel through here.
    await billing_service.enforce_quota(db, tenant_id, "documents")

    document_id = uuid.uuid4()
    storage_key = document_storage_key(tenant_id, document_id)
    # Envelope-encrypt the bytes, then persist the token to object storage.
    get_storage().put(storage_key, encrypt(data).to_token().encode("utf-8"))

    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=storage_key,
        encryption_key_version=settings.ENCRYPTION_KEY_VERSION,
        content_type=content_type,
        visibility=visibility,
        status=IngestionStatus.PENDING,
        chunk_count=0,
    )
    db.add(document)
    await db.flush()

    if segment_ids:
        await segment_service.replace_document_segments(
            db, tenant_id=tenant_id, document_id=document_id, segment_ids=segment_ids
        )

    await audit_service.write_event(
        db,
        tenant_id=tenant_id,
        action=AuditAction.DOCUMENT_UPLOADED,
        actor_user_id=owner_user_id,
        resource_type="document",
        resource_id=str(document_id),
        metadata={
            "filename": filename,
            "size_bytes": len(data),
            "content_type": content_type.value,
            "visibility": visibility.value,
            "source": source,
        },
        ip_address=ip_address,
    )

    # Queue ingestion (runs after the caller commits + the response is sent).
    background.add_task(process_document, document_id, trace_id)
    return document
