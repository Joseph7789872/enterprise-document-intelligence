"""AuditLog model — append-only record of every security-sensitive action.

Immutability is a security property: the model intentionally has no ``updated_at``
or ``deleted_at`` column, and the service layer exposes no mutate/delete path. A
future migration can add a DB-level append-only trigger / revoke UPDATE,DELETE on
this table for defense in depth (see Phase 0 threat model).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID, JSONBType


class AuditAction(str, enum.Enum):
    """Enumerated audit actions. Extend as new sensitive operations are added."""

    # Auth / identity
    TENANT_REGISTERED = "tenant.registered"
    USER_REGISTERED = "user.registered"
    LOGIN_SUCCEEDED = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    TOKEN_REFRESHED = "auth.token_refreshed"  # noqa: S105 - audit action name, not a secret
    # Audit
    AUDIT_READ = "audit.read"
    # Documents (Phase 1)
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_INGESTED = "document.ingested"
    DOCUMENT_INGESTION_FAILED = "document.ingestion_failed"
    DOCUMENT_VIEWED = "document.viewed"
    DOCUMENT_LISTED = "document.listed"
    SEARCH_PERFORMED = "search.performed"
    # Multi-agent query workflow (Phase 3)
    QUERY_SUBMITTED = "query.submitted"
    QUERY_ANSWERED = "query.answered"
    QUERY_PENDING_APPROVAL = "query.pending_approval"
    QUERY_APPROVED = "query.approved"
    QUERY_REJECTED = "query.rejected"
    LLM_CALL = "llm.call"
    # Evaluation + CI gate (Phase 4)
    EVAL_RUN_STARTED = "eval.run_started"
    EVAL_RUN_COMPLETED = "eval.run_completed"
    EVAL_RESULTS_VIEWED = "eval.results_viewed"
    # Access control + admin (Phase 5)
    GROUP_CREATED = "group.created"
    GROUP_DELETED = "group.deleted"
    GROUP_MEMBER_ADDED = "group.member_added"
    GROUP_MEMBER_REMOVED = "group.member_removed"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DEACTIVATED = "user.deactivated"
    PERMISSION_GRANTED = "acl.permission_granted"
    PERMISSION_REVOKED = "acl.permission_revoked"
    DOCUMENT_ACL_VIEWED = "acl.document_viewed"
    DOCUMENT_DELETED = "document.deleted"
    ACCESS_DENIED = "access.denied"
    # Compliance, observability + MCP (Phase 6)
    AUDIT_EXPORTED = "audit.exported"
    API_KEY_CREATED = "api_key.created"  # noqa: S105 - audit action name, not a secret
    API_KEY_REVOKED = "api_key.revoked"  # noqa: S105 - audit action name, not a secret
    MCP_TOOL_CALLED = "mcp.tool_called"
    DSR_RECEIVED = "compliance.dsr_received"
    DSR_FULFILLED = "compliance.dsr_fulfilled"
    COMPLIANCE_CONFIG_VIEWED = "compliance.config_viewed"
    # Self-hosted LLM routing + deployment (Phase 7)
    TENANT_SETTINGS_UPDATED = "tenant.settings_updated"
    LLM_ROUTE_DENIED = "llm.route_denied"
    # Manager-curated sales content (V1)
    RAMP_TOPIC_CREATED = "ramp_topic.created"
    RAMP_TOPIC_UPDATED = "ramp_topic.updated"
    RAMP_TOPIC_DELETED = "ramp_topic.deleted"
    OBJECTION_CREATED = "objection.created"
    OBJECTION_UPDATED = "objection.updated"
    OBJECTION_DELETED = "objection.deleted"
    # ICP / segments (Phase B)
    SEGMENT_CREATED = "segment.created"
    SEGMENT_UPDATED = "segment.updated"
    SEGMENT_DELETED = "segment.deleted"
    DOCUMENT_SEGMENTS_UPDATED = "document.segments_updated"
    # Time-to-value: templates + connectors (Phase C)
    TEMPLATE_APPLIED = "template.applied"
    URL_IMPORTED = "document.url_imported"
    CONNECTOR_TOKEN_SET = "connector.token_set"  # noqa: S105 - audit action name, not a secret
    CONNECTOR_SYNCED = "connector.synced"
    # Hosted SaaS: invites, password reset, billing (Phase D)
    USER_INVITED = "user.invited"
    INVITE_ACCEPTED = "invite.accepted"
    INVITE_REVOKED = "invite.revoked"
    PASSWORD_RESET_REQUESTED = "password.reset_requested"  # noqa: S105 - action name, not a secret
    PASSWORD_RESET_COMPLETED = "password.reset_completed"  # noqa: S105 - action name, not a secret
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    CHECKOUT_STARTED = "billing.checkout_started"
    BILLING_PORTAL_OPENED = "billing.portal_opened"
    # Manager analytics (Phase E)
    ANALYTICS_VIEWED = "analytics.viewed"
    ANALYTICS_EXPORTED = "analytics.exported"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # Primary access pattern: a tenant's recent events, newest first.
        Index("ix_audit_logs_tenant_id_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Not a FK with CASCADE: audit history must survive tenant/user deletion.
    tenant_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", native_enum=False, length=50),
        nullable=False,
    )
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Structured context. MUST NOT contain secrets, plaintext document content, or PII
    # beyond what is necessary to investigate an event.
    event_metadata: Mapped[dict | None] = mapped_column(JSONBType(), nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6-safe
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # "allow" | "deny" — makes denied access attempts first-class in the audit trail.
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AuditLog {self.action} tenant={self.tenant_id} at={self.created_at}>"
