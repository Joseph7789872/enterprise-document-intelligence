"""Ramp topic model — a manager-curated starter question for new-rep onboarding.

Each topic is a one-click prompt on the AE ramp checklist (e.g. "Pricing & packaging" →
"How is our product priced and packaged?"). Manager/admin curated, tenant-scoped.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class RampTopic(Base, TimestampMixin, TenantMixin):
    __tablename__ = "ramp_topics"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    suggested_question: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Lower sorts first; ties broken by created_at.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<RampTopic id={self.id} tenant={self.tenant_id} title={self.title!r}>"
