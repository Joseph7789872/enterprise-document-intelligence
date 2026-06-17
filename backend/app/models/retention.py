"""Compliance skeleton models.

Minimal tables created in Phase 0 so later phases (6: Compliance & Observability)
extend rather than introduce them. Kept deliberately small.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID, JSONBType


class DataRetentionPolicy(Base, TimestampMixin, TenantMixin):
    """How long a class of resource is retained before purge/anonymization."""

    __tablename__ = "data_retention_policies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # e.g. "document", "audit_log", "query_history"
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ComplianceEventType(str, enum.Enum):
    DSR_REQUESTED = "dsr.requested"
    DSR_FULFILLED = "dsr.fulfilled"
    RETENTION_PURGE = "retention.purge"
    POLICY_CHANGED = "policy.changed"


class ComplianceEvent(Base, TimestampMixin, TenantMixin):
    """Compliance-relevant lifecycle events (GDPR DSRs, retention purges, etc.)."""

    __tablename__ = "compliance_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[ComplianceEventType] = mapped_column(
        Enum(ComplianceEventType, name="compliance_event_type", native_enum=False, length=50),
        nullable=False,
    )
    details: Mapped[dict | None] = mapped_column(JSONBType(), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
