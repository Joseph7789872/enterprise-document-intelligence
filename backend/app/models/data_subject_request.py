"""DataSubjectRequest model — a GDPR/CCPA data-subject request lifecycle.

Tracks ACCESS / EXPORT / ERASURE requests for a data subject (a user) within a tenant.
``result`` holds the export bundle (for access/export) or a summary of what was erased.
The associated :class:`ComplianceEvent` rows record the audit trail; ``audit_logs`` are
never erased (retained on a legal-obligation basis — see the compliance service).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID, JSONBType


class DSRType(str, enum.Enum):
    ACCESS = "access"
    EXPORT = "export"
    ERASURE = "erasure"


class DSRStatus(str, enum.Enum):
    RECEIVED = "received"
    IN_PROGRESS = "in_progress"
    FULFILLED = "fulfilled"
    REJECTED = "rejected"


class DataSubjectRequest(Base, TimestampMixin, TenantMixin):
    __tablename__ = "data_subject_requests"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    subject_email: Mapped[str] = mapped_column(String(320), nullable=False)
    request_type: Mapped[DSRType] = mapped_column(
        Enum(DSRType, name="dsr_type", native_enum=False, length=20), nullable=False
    )
    status: Mapped[DSRStatus] = mapped_column(
        Enum(DSRStatus, name="dsr_status", native_enum=False, length=20),
        nullable=False,
        default=DSRStatus.RECEIVED,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONBType(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<DataSubjectRequest id={self.id} type={self.request_type} status={self.status}>"
