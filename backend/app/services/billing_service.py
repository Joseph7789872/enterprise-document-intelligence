"""Billing — plans, plan-limit enforcement, and a swappable payment provider (Phase D).

Plan-limit enforcement (``enforce_quota``) is always built but only *activates* when
``settings.ENABLE_BILLING`` is on, so turning billing off restores the pre-Phase-D
unlimited behavior. The payment integration is an injectable :class:`BillingProvider`
(mirrors ``get_fetcher`` / ``get_email_sender``): tests drive the deterministic
:class:`FakeBillingProvider`; production resolves :class:`StripeBillingProvider` (which
lazy-imports the optional ``stripe`` SDK). The provider normalizes Stripe webhooks into a
:class:`BillingEvent` so ``apply_webhook_event`` stays provider-agnostic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import PlanLimitError
from app.models.invitation import Invitation, InvitationStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant import Tenant
from app.services import usage_service
from app.services.plans_data import PLANS, Plan, get_plan

Resource = Literal["seats", "documents", "queries"]


# ── Subscription helpers ─────────────────────────────────────────────────────────────
async def subscription_for(db: AsyncSession, tenant_id: uuid.UUID) -> Subscription | None:
    return await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))


def plan_for(sub: Subscription | None) -> Plan:
    """Resolve a subscription to its Plan, defaulting to the configured trial plan."""
    if sub is not None:
        plan = get_plan(sub.plan_key)
        if plan is not None:
            return plan
    return PLANS.get(settings.DEFAULT_PLAN_KEY) or next(iter(PLANS.values()))


async def ensure_subscription(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    plan_key: str | None = None,
    status: SubscriptionStatus = SubscriptionStatus.TRIALING,
) -> Subscription:
    """Create the tenant's subscription row if absent (called at signup). Idempotent."""
    existing = await subscription_for(db, tenant_id)
    if existing is not None:
        return existing
    key = plan_key or settings.DEFAULT_PLAN_KEY
    plan = get_plan(key) or next(iter(PLANS.values()))
    sub = Subscription(
        tenant_id=tenant_id,
        plan_key=plan.key,
        status=status,
        seats=plan.limits.seats or 0,
    )
    db.add(sub)
    await db.flush()
    return sub


# ── Quota enforcement ────────────────────────────────────────────────────────────────
async def _current_count(db: AsyncSession, tenant_id: uuid.UUID, resource: Resource) -> int:
    if resource == "documents":
        return await usage_service.count_documents(db, tenant_id)
    if resource == "queries":
        return await usage_service.count_queries_this_period(db, tenant_id)
    # seats: active users + still-pending invites (an unaccepted invite reserves a seat).
    active = await usage_service.count_active_users(db, tenant_id)
    pending = int(
        await db.scalar(
            select(func.count())
            .select_from(Invitation)
            .where(
                Invitation.tenant_id == tenant_id,
                Invitation.status == InvitationStatus.PENDING,
            )
        )
        or 0
    )
    return active + pending


def _limit_for(plan: Plan, resource: Resource) -> int | None:
    return {
        "seats": plan.limits.seats,
        "documents": plan.limits.documents,
        "queries": plan.limits.queries_per_month,
    }[resource]


async def enforce_quota(db: AsyncSession, tenant_id: uuid.UUID, resource: Resource) -> None:
    """Raise :class:`PlanLimitError` if adding one more ``resource`` would exceed the plan.

    No-op when billing is disabled — preserves the pre-Phase-D unlimited behavior.
    """
    if not settings.ENABLE_BILLING:
        return
    plan = plan_for(await subscription_for(db, tenant_id))
    limit = _limit_for(plan, resource)
    if limit is None:  # unlimited
        return
    if await _current_count(db, tenant_id, resource) >= limit:
        raise PlanLimitError(
            f"Your {plan.name} plan allows {limit} {resource}. Upgrade to add more."
        )


# ── Provider abstraction ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class BillingEvent:
    """A normalized billing state-change, parsed from a provider webhook."""

    tenant_id: uuid.UUID
    plan_key: str
    status: SubscriptionStatus
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    current_period_end: datetime | None = None


class BillingError(Exception):
    """A billing-provider operation failed (bad webhook signature, API error)."""


class BillingProvider(Protocol):
    async def create_checkout_session(
        self, *, tenant: Tenant, plan: Plan, customer_email: str, success_url: str, cancel_url: str
    ) -> str: ...

    async def create_portal_session(
        self, *, tenant: Tenant, sub: Subscription | None, return_url: str
    ) -> str: ...

    def parse_webhook(self, payload: bytes, signature: str) -> BillingEvent: ...


class FakeBillingProvider:
    """Deterministic, offline provider for dev/test. ``parse_webhook`` accepts a plain JSON
    body (``{tenant_id, plan_key, status}``) so tests can drive subscription changes without
    Stripe; the signature is ignored."""

    async def create_checkout_session(
        self, *, tenant: Tenant, plan: Plan, customer_email: str, success_url: str, cancel_url: str
    ) -> str:
        return f"https://billing.local/fake-checkout/{tenant.id}?plan={plan.key}"

    async def create_portal_session(
        self, *, tenant: Tenant, sub: Subscription | None, return_url: str
    ) -> str:
        return f"https://billing.local/fake-portal/{tenant.id}"

    def parse_webhook(self, payload: bytes, signature: str) -> BillingEvent:
        import json

        try:
            data = json.loads(payload.decode("utf-8"))
            return BillingEvent(
                tenant_id=uuid.UUID(str(data["tenant_id"])),
                plan_key=str(data["plan_key"]),
                status=SubscriptionStatus(str(data.get("status", "active"))),
                stripe_customer_id=data.get("stripe_customer_id"),
                stripe_subscription_id=data.get("stripe_subscription_id"),
            )
        except (ValueError, KeyError) as exc:
            raise BillingError(f"Malformed fake webhook payload: {exc}") from exc


class StripeBillingProvider:
    """Real Stripe integration (lazy-imports the optional ``stripe`` SDK)."""

    def _client(self):  # type: ignore[no-untyped-def]
        import stripe

        stripe.api_key = settings.STRIPE_API_KEY
        return stripe

    async def create_checkout_session(
        self, *, tenant: Tenant, plan: Plan, customer_email: str, success_url: str, cancel_url: str
    ) -> str:
        stripe = self._client()
        price_id = getattr(settings, plan.stripe_price_setting or "", "")
        if not price_id:
            raise BillingError(f"No Stripe price configured for plan {plan.key!r}.")
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=customer_email,
            client_reference_id=str(tenant.id),
            metadata={"tenant_id": str(tenant.id), "plan_key": plan.key},
            subscription_data={"metadata": {"tenant_id": str(tenant.id), "plan_key": plan.key}},
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return str(session.url)

    async def create_portal_session(
        self, *, tenant: Tenant, sub: Subscription | None, return_url: str
    ) -> str:
        stripe = self._client()
        if sub is None or not sub.stripe_customer_id:
            raise BillingError("No Stripe customer for this tenant yet.")
        session = stripe.billing_portal.Session.create(
            customer=sub.stripe_customer_id, return_url=return_url
        )
        return str(session.url)

    def parse_webhook(self, payload: bytes, signature: str) -> BillingEvent:
        stripe = self._client()
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.STRIPE_WEBHOOK_SECRET
            )
        except Exception as exc:  # noqa: BLE001 - stripe raises several types
            raise BillingError(f"Invalid Stripe webhook: {exc}") from exc

        obj = event["data"]["object"]
        meta = obj.get("metadata") or {}
        tenant_raw = meta.get("tenant_id") or obj.get("client_reference_id")
        if not tenant_raw:
            raise BillingError("Stripe event has no tenant_id in metadata.")

        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "trialing": SubscriptionStatus.TRIALING,
            "past_due": SubscriptionStatus.PAST_DUE,
            "unpaid": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELED,
        }
        if event["type"] == "customer.subscription.deleted":
            status = SubscriptionStatus.CANCELED
        else:
            status = status_map.get(obj.get("status", "active"), SubscriptionStatus.ACTIVE)

        period_end = obj.get("current_period_end")
        return BillingEvent(
            tenant_id=uuid.UUID(str(tenant_raw)),
            plan_key=str(meta.get("plan_key") or "pro"),
            status=status,
            stripe_customer_id=obj.get("customer"),
            stripe_subscription_id=obj.get("id") if obj.get("object") == "subscription" else None,
            current_period_end=(
                datetime.fromtimestamp(period_end, tz=UTC) if period_end else None
            ),
        )


# Test-injectable override (explicit hook, like the fetcher's).
_override: BillingProvider | None = None


def set_billing_provider(provider: BillingProvider | None) -> None:
    global _override
    _override = provider


def get_billing_provider() -> BillingProvider:
    if _override is not None:
        return _override
    if settings.effective_billing_provider == "stripe":
        return StripeBillingProvider()
    return FakeBillingProvider()


# ── Webhook application ──────────────────────────────────────────────────────────────
async def apply_webhook_event(db: AsyncSession, event: BillingEvent) -> Subscription:
    """Upsert the tenant's subscription from a normalized provider event."""
    sub = await subscription_for(db, event.tenant_id)
    if sub is None:
        sub = Subscription(tenant_id=event.tenant_id, plan_key=event.plan_key, status=event.status)
        db.add(sub)
    sub.plan_key = event.plan_key
    sub.status = event.status
    if event.stripe_customer_id:
        sub.stripe_customer_id = event.stripe_customer_id
    if event.stripe_subscription_id:
        sub.stripe_subscription_id = event.stripe_subscription_id
    if event.current_period_end:
        sub.current_period_end = event.current_period_end
    plan = get_plan(event.plan_key)
    if plan is not None and plan.limits.seats is not None:
        sub.seats = plan.limits.seats
    await db.flush()
    return sub
