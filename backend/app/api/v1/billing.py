"""Billing endpoints (Phase D) — plan, usage, checkout, portal, and the Stripe webhook.

Mounted only when ``ENABLE_BILLING`` is on (see api/router.py), so the whole surface 404s
in deployments that don't bill. Checkout/portal are manager-only; the webhook is
unauthenticated but signature-verified by the provider.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser, client_ip, get_current_user, get_db, require_role
from app.errors import AppError, NotFoundError
from app.models.audit_log import AuditAction
from app.models.subscription import SubscriptionStatus
from app.models.tenant import Tenant
from app.models.user import UserRole
from app.schemas.billing import (
    BillingOverview,
    CheckoutRequest,
    CheckoutResponse,
    PlanInfo,
    PlanLimitsOut,
    PortalResponse,
    SubscriptionRead,
    UsageOut,
)
from app.services import audit_service, billing_service, usage_service
from app.services.billing_service import BillingError
from app.services.plans_data import PLANS, Plan, get_plan

router = APIRouter(prefix="/billing", tags=["billing"])

_manager = require_role(UserRole.OWNER, UserRole.ADMIN)


def _plan_info(plan: Plan) -> PlanInfo:
    return PlanInfo(
        key=plan.key,
        name=plan.name,
        price_display=plan.price_display,
        limits=PlanLimitsOut(
            seats=plan.limits.seats,
            documents=plan.limits.documents,
            queries_per_month=plan.limits.queries_per_month,
        ),
    )


@router.get("", response_model=BillingOverview)
async def get_billing(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BillingOverview:
    """The caller's tenant subscription, its plan, and current usage."""
    sub = await billing_service.subscription_for(db, current.tenant_id)
    plan = billing_service.plan_for(sub)
    usage = await usage_service.snapshot(db, current.tenant_id)
    sub_read = (
        SubscriptionRead(
            plan_key=sub.plan_key,
            status=sub.status,
            seats=sub.seats,
            current_period_end=sub.current_period_end,
        )
        if sub is not None
        else SubscriptionRead(
            plan_key=plan.key,
            status=SubscriptionStatus.TRIALING,
            seats=plan.limits.seats or 0,
            current_period_end=None,
        )
    )
    return BillingOverview(
        subscription=sub_read,
        plan=_plan_info(plan),
        usage=UsageOut(
            users=usage.users,
            documents=usage.documents,
            queries_this_period=usage.queries_this_period,
        ),
    )


@router.get("/plans", response_model=list[PlanInfo])
async def list_plans(
    current: CurrentUser = Depends(get_current_user),
) -> list[PlanInfo]:
    return [_plan_info(p) for p in PLANS.values()]


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(
    body: CheckoutRequest,
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """Begin a checkout for ``plan_key`` and return the provider's hosted checkout URL."""
    plan = get_plan(body.plan_key)
    if plan is None:
        raise NotFoundError("Unknown plan.")
    tenant = await db.get(Tenant, current.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    try:
        url = await billing_service.get_billing_provider().create_checkout_session(
            tenant=tenant,
            plan=plan,
            customer_email=current.email,
            success_url=body.success_url or f"{base}/billing?status=success",
            cancel_url=body.cancel_url or f"{base}/billing?status=cancel",
        )
    except BillingError as exc:
        raise AppError(str(exc)) from exc
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.CHECKOUT_STARTED,
        actor_user_id=current.id,
        resource_type="subscription",
        metadata={"plan_key": plan.key},
        ip_address=client_ip(request),
        outcome="allow",
    )
    return CheckoutResponse(checkout_url=url)


@router.post("/portal", response_model=PortalResponse)
async def open_portal(
    request: Request,
    current: CurrentUser = Depends(_manager),
    db: AsyncSession = Depends(get_db),
) -> PortalResponse:
    """Return a link to the provider's billing portal (manage card / cancel)."""
    tenant = await db.get(Tenant, current.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    sub = await billing_service.subscription_for(db, current.tenant_id)
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    try:
        url = await billing_service.get_billing_provider().create_portal_session(
            tenant=tenant, sub=sub, return_url=f"{base}/billing"
        )
    except BillingError as exc:
        raise AppError(str(exc)) from exc
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.BILLING_PORTAL_OPENED,
        actor_user_id=current.id,
        resource_type="subscription",
        ip_address=client_ip(request),
        outcome="allow",
    )
    return PortalResponse(portal_url=url)


@router.post("/webhook")
async def billing_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Provider webhook (unauthenticated; signature-verified). Updates the subscription."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = billing_service.get_billing_provider().parse_webhook(payload, signature)
    except BillingError as exc:
        raise AppError(str(exc)) from exc
    sub = await billing_service.apply_webhook_event(db, event)
    await audit_service.write_event(
        db,
        tenant_id=event.tenant_id,
        action=AuditAction.SUBSCRIPTION_UPDATED,
        resource_type="subscription",
        resource_id=str(sub.id),
        metadata={"plan_key": sub.plan_key, "status": sub.status.value},
    )
    return {"received": True}
