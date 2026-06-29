"""Billing plans (in-repo constants).

The set of plans a tenant can be on, with their seat / document / monthly-query limits.
Pure data — :mod:`app.services.billing_service` enforces these limits and maps a plan to a
Stripe price id (read from settings at checkout time, so price ids stay in env/secrets, not
in code). ``None`` on a limit means unlimited.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    seats: int | None
    documents: int | None
    queries_per_month: int | None


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_display: str
    limits: PlanLimits
    # Name of the settings attribute holding this plan's Stripe price id (or None for the
    # free trial, which never goes through checkout). Resolved lazily in billing_service.
    stripe_price_setting: str | None = None


PLANS: dict[str, Plan] = {
    "trial": Plan(
        key="trial",
        name="Trial",
        price_display="Free",
        limits=PlanLimits(seats=3, documents=25, queries_per_month=200),
        stripe_price_setting=None,
    ),
    "pro": Plan(
        key="pro",
        name="Pro",
        price_display="$49 / seat / mo",
        limits=PlanLimits(seats=15, documents=500, queries_per_month=5_000),
        stripe_price_setting="STRIPE_PRICE_PRO",
    ),
    "business": Plan(
        key="business",
        name="Business",
        price_display="$99 / seat / mo",
        limits=PlanLimits(seats=None, documents=None, queries_per_month=None),
        stripe_price_setting="STRIPE_PRICE_BUSINESS",
    ),
}


def get_plan(plan_key: str) -> Plan | None:
    return PLANS.get(plan_key)
