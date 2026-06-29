"""Subscription — a tenant's billing plan + state (Phase D).

One row per tenant (created at signup on the trial plan). ``plan_key`` references a plan
defined in ``services/plans_data.py``; the Stripe ids are populated once a tenant checks
out. Plan limits are enforced from ``billing_service`` only when ``ENABLE_BILLING`` is on.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class Subscription(Base, TimestampMixin, TenantMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_subscriptions_tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    plan_key: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False, length=20),
        nullable=False,
        default=SubscriptionStatus.TRIALING,
    )
    # Purchased seats (defaults from the plan); seat-limit checks compare active users to this.
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Subscription tenant={self.tenant_id} plan={self.plan_key} status={self.status}>"
