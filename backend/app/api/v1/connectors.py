"""Content connector endpoints (Phase C) — Notion via integration token.

Manager-only. The token is stored encrypted (``crypto.encrypt_str``) and never returned.
``sync`` lists the integration's shared pages, assembles each page's text, and funnels it
through the shared :func:`intake_document` path (so connector content is scanned,
encrypted, and ingested exactly like an upload).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_str, encrypt_str
from app.core.deps import CurrentUser, client_ip, get_db, require_role
from app.core.logging import get_trace_id
from app.errors import AppError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.connector_credential import ConnectorCredential, ConnectorProvider
from app.models.document import ContentVisibility, SalesContentType
from app.models.user import UserRole
from app.schemas.connector import NotionStatus, NotionSyncResponse, NotionTokenRequest
from app.schemas.document import BatchItemResult
from app.services import audit_service
from app.services.connectors import notion as notion_client
from app.services.ingestion_intake import IntakeError, intake_document

router = APIRouter(prefix="/connectors", tags=["connectors"])

_manager = require_role(UserRole.OWNER, UserRole.ADMIN)


class NotionSyncError(AppError):
    status_code = 422
    message = "Notion sync failed."


async def _load(
    db: AsyncSession, tenant_id: uuid.UUID, provider: ConnectorProvider
) -> ConnectorCredential | None:
    return (
        await db.scalars(
            select(ConnectorCredential).where(
                ConnectorCredential.tenant_id == tenant_id,
                ConnectorCredential.provider == provider,
            )
        )
    ).first()


@router.put("/notion/token", response_model=NotionStatus)
async def set_notion_token(
    body: NotionTokenRequest,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> NotionStatus:
    """Store (encrypted) the tenant's Notion integration token. Never returned thereafter."""
    cred = await _load(db, current.tenant_id, ConnectorProvider.NOTION)
    if cred is None:
        cred = ConnectorCredential(
            tenant_id=current.tenant_id,
            provider=ConnectorProvider.NOTION,
            token_encrypted=encrypt_str(body.token),
            enabled=True,
        )
        db.add(cred)
    else:
        cred.token_encrypted = encrypt_str(body.token)
        cred.enabled = True
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.CONNECTOR_TOKEN_SET,
        actor_user_id=current.id,
        resource_type="connector",
        resource_id="notion",
        ip_address=client_ip(request),
        outcome="allow",
    )
    return NotionStatus(connected=True, enabled=cred.enabled, last_synced_at=cred.last_synced_at)


@router.get("/notion", response_model=NotionStatus)
async def notion_status(
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> NotionStatus:
    """Whether a Notion token is stored, and when it last synced. Never returns the token."""
    cred = await _load(db, current.tenant_id, ConnectorProvider.NOTION)
    if cred is None:
        return NotionStatus(connected=False)
    return NotionStatus(connected=True, enabled=cred.enabled, last_synced_at=cred.last_synced_at)


@router.post("/notion/sync", response_model=NotionSyncResponse)
async def sync_notion(
    request: Request,
    background: BackgroundTasks,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> NotionSyncResponse:
    """Import the integration's shared Notion pages as documents."""
    cred = await _load(db, current.tenant_id, ConnectorProvider.NOTION)
    if cred is None:
        raise NotFoundError("No Notion token configured.")
    token = decrypt_str(cred.token_encrypted)

    try:
        pages = await notion_client.get_notion_client().list_pages(token)
    except notion_client.NotionError as exc:
        raise NotionSyncError(f"Notion sync failed: {exc}") from exc

    results: list[BatchItemResult] = []
    for page in pages:
        try:
            doc = await intake_document(
                db,
                tenant_id=current.tenant_id,
                owner_user_id=current.id,
                filename=f"{page.title}.txt",
                mime_type="text/plain",
                data=page.text.encode("utf-8"),
                content_type=SalesContentType.PRODUCT,
                visibility=ContentVisibility.REP_VISIBLE,
                segment_ids=[],
                background=background,
                trace_id=get_trace_id(),
                source="notion_sync",
                ip_address=client_ip(request),
            )
            results.append(BatchItemResult(filename=page.title, status="accepted", id=doc.id))
        except IntakeError as exc:
            results.append(
                BatchItemResult(filename=page.title, status="rejected", error=exc.reason)
            )

    from datetime import UTC, datetime

    cred.last_synced_at = datetime.now(UTC)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.CONNECTOR_SYNCED,
        actor_user_id=current.id,
        resource_type="connector",
        resource_id="notion",
        metadata={"pages": len(results), "accepted": sum(r.status == "accepted" for r in results)},
        ip_address=client_ip(request),
        outcome="allow",
    )
    await db.commit()
    return NotionSyncResponse(results=results)
