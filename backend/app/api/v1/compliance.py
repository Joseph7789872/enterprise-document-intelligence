"""Compliance endpoints: config snapshot, retention policies, and GDPR DSRs.

All endpoints are OWNER/ADMIN only and strictly tenant-scoped. DSR fulfillment records
both an audit event and a ``ComplianceEvent`` for the compliance trail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_db, require_role
from app.errors import ConflictError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.data_subject_request import DataSubjectRequest, DSRStatus, DSRType
from app.models.retention import ComplianceEvent, ComplianceEventType, DataRetentionPolicy
from app.models.user import UserRole
from app.schemas.compliance import (
    DSRCreate,
    DSRRead,
    RetentionPolicyRead,
    RetentionPolicyUpsert,
)
from app.services import audit_service, compliance_service

router = APIRouter(prefix="/compliance", tags=["compliance"])

_admin = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get("/config")
async def get_compliance_config(
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    config = await compliance_service.compliance_config(db, current.tenant_id)
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.COMPLIANCE_CONFIG_VIEWED,
        actor_user_id=current.id,
        resource_type="compliance",
        ip_address=client_ip(request),
    )
    return config


# ── Retention policies ─────────────────────────────────────────────────────────────
@router.get("/retention", response_model=list[RetentionPolicyRead])
async def list_retention_policies(
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DataRetentionPolicy]:
    rows = await db.scalars(
        select(DataRetentionPolicy).where(DataRetentionPolicy.tenant_id == current.tenant_id)
    )
    return list(rows.all())


@router.put("/retention", response_model=RetentionPolicyRead)
async def upsert_retention_policy(
    body: RetentionPolicyUpsert,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> DataRetentionPolicy:
    policy = await db.scalar(
        select(DataRetentionPolicy).where(
            DataRetentionPolicy.tenant_id == current.tenant_id,
            DataRetentionPolicy.resource_type == body.resource_type,
        )
    )
    if policy is None:
        policy = DataRetentionPolicy(
            tenant_id=current.tenant_id,
            resource_type=body.resource_type,
            retention_days=body.retention_days,
            description=body.description,
        )
        db.add(policy)
    else:
        policy.retention_days = body.retention_days
        policy.description = body.description
    await db.flush()
    return policy


# ── Data Subject Requests ──────────────────────────────────────────────────────────
async def _compliance_event(
    db: AsyncSession, tenant_id: uuid.UUID, event_type: ComplianceEventType, details: dict
) -> None:
    db.add(ComplianceEvent(tenant_id=tenant_id, event_type=event_type, details=details))
    await db.flush()


@router.post("/ds-request", response_model=DSRRead, status_code=status.HTTP_201_CREATED)
async def create_dsr(
    body: DSRCreate,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequest:
    subject = await compliance_service.resolve_subject(
        db, current.tenant_id, subject_user_id=body.subject_user_id, email=body.subject_email
    )
    dsr = DataSubjectRequest(
        tenant_id=current.tenant_id,
        subject_user_id=subject.id if subject else body.subject_user_id,
        subject_email=body.subject_email.lower(),
        request_type=body.request_type,
        status=DSRStatus.RECEIVED,
        requested_by_user_id=current.id,
    )
    db.add(dsr)
    await db.flush()
    await _compliance_event(
        db, current.tenant_id, ComplianceEventType.DSR_REQUESTED,
        {"dsr_id": str(dsr.id), "type": body.request_type.value},
    )
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.DSR_RECEIVED,
        actor_user_id=current.id,
        resource_type="dsr",
        resource_id=str(dsr.id),
        metadata={"type": body.request_type.value},
        ip_address=client_ip(request),
    )
    return dsr


@router.get("/ds-request", response_model=list[DSRRead])
async def list_dsrs(
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DataSubjectRequest]:
    rows = await db.scalars(
        select(DataSubjectRequest)
        .where(DataSubjectRequest.tenant_id == current.tenant_id)
        .order_by(DataSubjectRequest.created_at.desc())
    )
    return list(rows.all())


async def _load_dsr(
    db: AsyncSession, current: CurrentUser, dsr_id: uuid.UUID
) -> DataSubjectRequest:
    dsr = await db.get(DataSubjectRequest, dsr_id)
    if dsr is None or dsr.tenant_id != current.tenant_id:
        raise NotFoundError("Data subject request not found.")
    return dsr


@router.get("/ds-request/{dsr_id}", response_model=DSRRead)
async def get_dsr(
    dsr_id: uuid.UUID,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequest:
    return await _load_dsr(db, current, dsr_id)


@router.post("/ds-request/{dsr_id}/fulfill", response_model=DSRRead)
async def fulfill_dsr(
    dsr_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(_admin),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequest:
    dsr = await _load_dsr(db, current, dsr_id)
    if dsr.status == DSRStatus.FULFILLED:
        raise ConflictError("This request has already been fulfilled.")

    subject = await compliance_service.resolve_subject(
        db, current.tenant_id, subject_user_id=dsr.subject_user_id, email=dsr.subject_email
    )
    if subject is None:
        dsr.status = DSRStatus.REJECTED
        dsr.result = {"error": "subject not found in tenant"}
        await db.flush()
        return dsr

    if dsr.request_type in (DSRType.ACCESS, DSRType.EXPORT):
        dsr.result = await compliance_service.build_export_bundle(db, current.tenant_id, subject)
    else:  # ERASURE
        dsr.result = await compliance_service.erase_subject(db, current.tenant_id, subject)

    dsr.status = DSRStatus.FULFILLED
    dsr.completed_at = datetime.now(UTC)
    await db.flush()

    await _compliance_event(
        db, current.tenant_id, ComplianceEventType.DSR_FULFILLED,
        {"dsr_id": str(dsr.id), "type": dsr.request_type.value},
    )
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.DSR_FULFILLED,
        actor_user_id=current.id,
        resource_type="dsr",
        resource_id=str(dsr.id),
        metadata={"type": dsr.request_type.value},
        ip_address=client_ip(request),
        outcome="allow",
    )
    return dsr
