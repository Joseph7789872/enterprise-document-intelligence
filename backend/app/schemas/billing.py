"""Billing API schemas (Phase D)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.subscription import SubscriptionStatus


class PlanLimitsOut(BaseModel):
    seats: int | None
    documents: int | None
    queries_per_month: int | None


class PlanInfo(BaseModel):
    key: str
    name: str
    price_display: str
    limits: PlanLimitsOut


class UsageOut(BaseModel):
    users: int
    documents: int
    queries_this_period: int


class SubscriptionRead(BaseModel):
    plan_key: str
    status: SubscriptionStatus
    seats: int
    current_period_end: datetime | None


class BillingOverview(BaseModel):
    subscription: SubscriptionRead
    plan: PlanInfo
    usage: UsageOut


class CheckoutRequest(BaseModel):
    plan_key: str
    # Where Stripe redirects after success/cancel (defaults applied server-side if omitted).
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str
