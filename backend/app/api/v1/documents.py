"""Document endpoints: upload, list, get."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt
from app.core.deps import CurrentUser, client_ip, get_current_user, get_db, require_role
from app.core.logging import get_trace_id
from app.errors import AppError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.document import ClassificationLevel, Document, IngestionStatus
from app.models.document_access_control import DocumentAccessControl, PrincipalType
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.acl import ACLGrantCreate, ACLGrantRead
from app.schemas.document import DocumentRead, UploadResponse
from app.services import audit_service, authz
from app.services.authz import Permission
from app.services.ingestion import process_document
from app.storage import document_storage_key, get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


class PayloadTooLargeError(AppError):
    status_code = 413
    message = "Uploaded file exceeds the maximum allowed size."


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    message = "Unsupported file type."


class MalwareDetectedError(AppError):
    status_code = 422
    message = "Uploaded file was rejected by malware scanning."


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    classification_level: ClassificationLevel = Form(ClassificationLevel.INTERNAL),
    department: str | None = Form(None),
    current: CurrentUser = Depends(
        require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.MEMBER)
    ),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Accept a document, store it encrypted, and queue background ingestion."""
    filename = file.filename or "upload"
    ext = _extension(filename)
    if ext not in settings.allowed_upload_extensions:
        raise UnsupportedMediaTypeError(
            f"Unsupported file type '.{ext}'. Allowed: "
            f"{', '.join(sorted(settings.allowed_upload_extensions))}."
        )

    # Read with a hard size cap (avoid buffering arbitrarily large uploads).
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit."
        )
    if not data:
        raise UnsupportedMediaTypeError("Uploaded file is empty.")

    # Malware gate — runs before anything touches storage.
    from app.services import malware_scan

    scan = malware_scan.scan(data)
    if not scan.clean:
        await audit_service.record_event_committed(
            tenant_id=current.tenant_id,
            action=AuditAction.DOCUMENT_UPLOADED,
            actor_user_id=current.id,
            resource_type="document",
            metadata={"rejected": "malware", "signature": scan.signature, "filename": filename},
            ip_address=client_ip(request),
            trace_id=get_trace_id(),
        )
        raise MalwareDetectedError(f"Malware signature detected: {scan.signature}.")

    document_id = uuid.uuid4()
    sha256 = hashlib.sha256(data).hexdigest()
    storage_key = document_storage_key(current.tenant_id, document_id)

    # Envelope-encrypt the bytes, then persist the token to object storage.
    token = encrypt(data).to_token().encode("utf-8")
    get_storage().put(storage_key, token)

    document = Document(
        id=document_id,
        tenant_id=current.tenant_id,
        owner_user_id=current.id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        sha256=sha256,
        storage_key=storage_key,
        encryption_key_version=settings.ENCRYPTION_KEY_VERSION,
        classification_level=classification_level,
        department=department,
        status=IngestionStatus.PENDING,
        chunk_count=0,
    )
    db.add(document)
    await db.flush()

    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.DOCUMENT_UPLOADED,
        actor_user_id=current.id,
        resource_type="document",
        resource_id=str(document_id),
        metadata={
            "filename": filename,
            "size_bytes": len(data),
            "classification_level": classification_level.value,
        },
        ip_address=client_ip(request),
    )
    await db.commit()

    # Queue ingestion after the response is sent.
    background.add_task(process_document, document_id, get_trace_id())

    return UploadResponse(id=document_id, filename=filename, status=IngestionStatus.PENDING)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    # Deny-by-default: non-privileged users see only documents they may VIEW.
    allowed = await authz.accessible_document_ids(
        db,
        tenant_id=current.tenant_id,
        user_id=current.id,
        role=current.role,
        permission=Permission.VIEW,
    )
    stmt = (
        select(Document)
        .where(Document.tenant_id == current.tenant_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    if allowed is not None:
        stmt = stmt.where(Document.id.in_(allowed))
    result = await db.scalars(stmt.limit(limit).offset(offset))
    documents = list(result.all())
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.DOCUMENT_LISTED,
        actor_user_id=current.id,
        resource_type="document",
        metadata={"returned": len(documents), "limit": limit, "offset": offset},
        ip_address=client_ip(request),
    )
    return documents


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    document = await db.get(Document, document_id)
    # Cross-tenant access — or lacking VIEW permission — is indistinguishable from
    # "not found" (no existence disclosure).
    if (
        document is None
        or document.tenant_id != current.tenant_id
        or document.deleted_at is not None
    ):
        raise NotFoundError("Document not found.")
    if not await authz.can_access_document(
        db,
        tenant_id=current.tenant_id,
        user_id=current.id,
        role=current.role,
        document_id=document.id,
        permission=Permission.VIEW,
    ):
        raise NotFoundError("Document not found.")

    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.DOCUMENT_VIEWED,
        actor_user_id=current.id,
        resource_type="document",
        resource_id=str(document.id),
        ip_address=client_ip(request),
    )
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a document. Requires CanDelete (owner/admin or an ACL grant).

    No VIEW access ⇒ 404 (don't leak existence); VIEW but no DELETE ⇒ 403.
    """
    document = await db.get(Document, document_id)
    if (
        document is None
        or document.tenant_id != current.tenant_id
        or document.deleted_at is not None
    ):
        raise NotFoundError("Document not found.")
    if not await authz.can_access_document(
        db, tenant_id=current.tenant_id, user_id=current.id, role=current.role,
        document_id=document.id, permission=Permission.VIEW,
    ):
        raise NotFoundError("Document not found.")

    # VIEW but not DELETE → audited 403.
    await authz.assert_can(
        db, tenant_id=current.tenant_id, user_id=current.id, role=current.role,
        document_id=document.id, permission=Permission.DELETE, ip_address=client_ip(request),
    )

    document.deleted_at = datetime.now(UTC)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.DOCUMENT_DELETED,
        actor_user_id=current.id,
        resource_type="document",
        resource_id=str(document.id),
        ip_address=client_ip(request),
        outcome="allow",
    )


# ── ACL management (document sub-resource) ─────────────────────────────────────────
async def _manageable_document(
    db: AsyncSession, current: CurrentUser, document_id: uuid.UUID, request: Request
) -> Document:
    """Load a document the caller may MANAGE; 404 if absent/no VIEW, 403 if no MANAGE."""
    document = await db.get(Document, document_id)
    if (
        document is None
        or document.tenant_id != current.tenant_id
        or document.deleted_at is not None
    ):
        raise NotFoundError("Document not found.")
    if not await authz.can_access_document(
        db, tenant_id=current.tenant_id, user_id=current.id, role=current.role,
        document_id=document.id, permission=Permission.VIEW,
    ):
        raise NotFoundError("Document not found.")
    await authz.assert_can(
        db, tenant_id=current.tenant_id, user_id=current.id, role=current.role,
        document_id=document.id, permission=Permission.MANAGE, ip_address=client_ip(request),
    )
    return document


async def _validate_principal(
    db: AsyncSession, tenant_id: uuid.UUID, principal_type: PrincipalType, principal_id: uuid.UUID
) -> None:
    """Ensure the grant target is a user/group in the caller's tenant."""
    if principal_type == PrincipalType.USER:
        user = await db.get(User, principal_id)
        ok = user is not None and user.tenant_id == tenant_id and user.deleted_at is None
    else:
        grp = await db.get(Group, principal_id)
        ok = grp is not None and grp.tenant_id == tenant_id
    if not ok:
        raise NotFoundError("Principal not found in this tenant.")


@router.get("/{document_id}/acl", response_model=list[ACLGrantRead])
async def list_document_acl(
    document_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentAccessControl]:
    document = await _manageable_document(db, current, document_id, request)
    grants = list(
        (
            await db.scalars(
                select(DocumentAccessControl).where(
                    DocumentAccessControl.tenant_id == current.tenant_id,
                    DocumentAccessControl.document_id == document.id,
                )
            )
        ).all()
    )
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.DOCUMENT_ACL_VIEWED,
        actor_user_id=current.id,
        resource_type="document",
        resource_id=str(document.id),
        metadata={"returned": len(grants)},
        ip_address=client_ip(request),
    )
    return grants


@router.post("/{document_id}/acl", response_model=ACLGrantRead, status_code=status.HTTP_201_CREATED)
async def grant_document_acl(
    document_id: uuid.UUID,
    body: ACLGrantCreate,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentAccessControl:
    document = await _manageable_document(db, current, document_id, request)
    await _validate_principal(db, current.tenant_id, body.principal_type, body.principal_id)

    grant = DocumentAccessControl(
        tenant_id=current.tenant_id,
        document_id=document.id,
        principal_type=body.principal_type,
        principal_id=body.principal_id,
        permissions=[p.value for p in body.permissions],
        granted_by_user_id=current.id,
    )
    db.add(grant)
    await db.flush()
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.PERMISSION_GRANTED,
        actor_user_id=current.id,
        resource_type="document",
        resource_id=str(document.id),
        metadata={
            "principal_type": body.principal_type.value,
            "principal_id": str(body.principal_id),
            "permissions": [p.value for p in body.permissions],
        },
        ip_address=client_ip(request),
        outcome="allow",
    )
    return grant


@router.delete("/{document_id}/acl/{acl_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_document_acl(
    document_id: uuid.UUID,
    acl_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    document = await _manageable_document(db, current, document_id, request)
    grant = await db.get(DocumentAccessControl, acl_id)
    if (
        grant is None
        or grant.tenant_id != current.tenant_id
        or grant.document_id != document.id
    ):
        raise NotFoundError("Grant not found.")
    await db.delete(grant)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.PERMISSION_REVOKED,
        actor_user_id=current.id,
        resource_type="document",
        resource_id=str(document.id),
        metadata={"acl_id": str(acl_id)},
        ip_address=client_ip(request),
        outcome="allow",
    )
