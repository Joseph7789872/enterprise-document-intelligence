"""Compliance helpers: config snapshot, GDPR export bundles, and erasure.

The export bundle assembles everything the platform holds about a data subject (their
user record, owned documents' metadata, queries, and audit events). Erasure deletes the
subject's queries and anonymizes their user record, but **retains** ``audit_logs`` — they
are immutable and kept on a legal-obligation basis (security/compliance record-keeping),
which is a recognized lawful basis under GDPR Art. 17(3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_str
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.query import Query
from app.models.retention import DataRetentionPolicy
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantSettings


async def compliance_config(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any]:
    """A non-sensitive snapshot for compliance/sales due-diligence."""
    policies = list(
        (
            await db.scalars(
                select(DataRetentionPolicy).where(DataRetentionPolicy.tenant_id == tenant_id)
            )
        ).all()
    )
    # Sub-processors reflect the *effective* providers, so a self-hosted / air-gapped
    # deployment correctly reports that no third party processes customer data.
    sub_processors = []
    if settings.effective_llm_provider == "anthropic":
        sub_processors.append("Anthropic (LLM, zero-retention DPA)")
    if settings.effective_embedding_provider == "openai":
        sub_processors.append("OpenAI (embeddings)")
    if settings.feature_flags["cloud_tracing"]:
        sub_processors.append("Langfuse Cloud (tracing)")

    tenant = await db.get(Tenant, tenant_id)
    tenant_policy = TenantSettings.from_raw(tenant.settings if tenant is not None else None)

    return {
        "data_region": settings.DATA_REGION,
        "deployment_mode": settings.DEPLOYMENT_MODE,
        "encryption_at_rest": "AES-256-GCM envelope encryption",
        "encryption_in_transit": "TLS 1.3 (deployment-enforced)",
        "append_only_audit": True,
        "langfuse_io_capture": settings.LANGFUSE_CAPTURE_IO,
        "feature_flags": settings.feature_flags,
        "llm_routing": {
            "baseline_provider": settings.effective_llm_provider,
            "self_hosted_configured": settings.self_hosted_llm_configured,
            "sensitive_classification": tenant_policy.sensitive_classification,
            "require_self_hosted_llm": tenant_policy.require_self_hosted_llm,
        },
        "embedding_provider": settings.effective_embedding_provider,
        "sub_processors": sub_processors,
        "retention_policies": [
            {"resource_type": p.resource_type, "retention_days": p.retention_days}
            for p in policies
        ],
    }


async def resolve_subject(
    db: AsyncSession, tenant_id: uuid.UUID, *, subject_user_id: uuid.UUID | None, email: str
) -> User | None:
    if subject_user_id is not None:
        user = await db.get(User, subject_user_id)
        if user is not None and user.tenant_id == tenant_id:
            return user
        return None
    return await db.scalar(
        select(User).where(User.tenant_id == tenant_id, User.email == email.lower())
    )


async def build_export_bundle(
    db: AsyncSession, tenant_id: uuid.UUID, subject: User
) -> dict[str, Any]:
    """Assemble all data held about the subject (GDPR access/portability)."""
    documents = list(
        (
            await db.scalars(
                select(Document).where(
                    Document.tenant_id == tenant_id, Document.owner_user_id == subject.id
                )
            )
        ).all()
    )
    queries = list(
        (
            await db.scalars(
                select(Query).where(Query.tenant_id == tenant_id, Query.user_id == subject.id)
            )
        ).all()
    )
    events = list(
        (
            await db.scalars(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id, AuditLog.actor_user_id == subject.id)
                .order_by(AuditLog.created_at.desc())
                .limit(1000)
            )
        ).all()
    )
    return {
        "user": {
            "id": str(subject.id),
            "email": subject.email,
            "role": subject.role.value,
            "is_active": subject.is_active,
            "created_at": subject.created_at.isoformat(),
        },
        "documents": [
            {"id": str(d.id), "filename": d.filename, "status": d.status.value} for d in documents
        ],
        "queries": [
            {
                "id": str(q.id),
                "question": decrypt_str(q.question_encrypted),
                "answer": decrypt_str(q.answer_encrypted) if q.answer_encrypted else None,
                "created_at": q.created_at.isoformat(),
            }
            for q in queries
        ],
        "audit_events": [
            {"action": e.action.value, "created_at": e.created_at.isoformat()} for e in events
        ],
    }


async def erase_subject(db: AsyncSession, tenant_id: uuid.UUID, subject: User) -> dict[str, Any]:
    """Delete the subject's queries and anonymize their user record (audit retained)."""
    query_ids = list(
        (
            await db.scalars(
                select(Query.id).where(Query.tenant_id == tenant_id, Query.user_id == subject.id)
            )
        ).all()
    )
    if query_ids:
        await db.execute(delete(Query).where(Query.id.in_(query_ids)))

    subject.is_active = False
    subject.deleted_at = datetime.now(UTC)
    subject.email = f"erased-{subject.id}@redacted.invalid"
    await db.flush()

    return {
        "queries_deleted": len(query_ids),
        "user_anonymized": True,
        "audit_logs_retained": True,  # immutable; legal-obligation basis
        "documents_retained": True,  # tenant assets; owner anonymized
    }
