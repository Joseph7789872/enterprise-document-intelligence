"""Aggregate v1 API routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    analytics,
    audit,
    auth,
    compliance,
    conversations,
    documents,
    evals,
    health,
    objections,
    query,
    ramp,
    search,
    segments,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(query.router)
# Phase B: conversational chat threads (per-user).
api_router.include_router(conversations.router)
# Core admin (users, invitations, templates) — always on. The enterprise admin surfaces
# (groups, api-keys, tenant LLM settings) live on admin.enterprise_router, mounted below.
api_router.include_router(admin.router)
# V1 sales: manager-curated ramp checklist + objection library (AE-readable).
api_router.include_router(ramp.router)
api_router.include_router(objections.router)
# Phase B: ICP / segments (AE-readable list, manager CRUD).
api_router.include_router(segments.router)
# Phase E: manager analytics dashboard (manager-only, read-only over existing data).
api_router.include_router(analytics.router)

# Enterprise-only surfaces — mounted only when their v1 feature flag is on (off in the
# production sales product; on in dev/test so the suite still covers them). Each router
# also carries a request-time require_feature guard so the off-state is testable.
if settings.ENABLE_AUDIT:
    api_router.include_router(audit.router)
if settings.ENABLE_ENTERPRISE_ADMIN:
    api_router.include_router(admin.enterprise_router)
if settings.ENABLE_EVALS:
    api_router.include_router(evals.router)
if settings.ENABLE_COMPLIANCE:
    api_router.include_router(compliance.router)
# Phase C: external content connectors (Notion). External egress, off by default.
if settings.ENABLE_CONNECTORS:
    from app.api.v1 import connectors

    api_router.include_router(connectors.router)
# Phase D: billing (plans, usage, checkout, Stripe webhook). Off by default.
if settings.ENABLE_BILLING:
    from app.api.v1 import billing

    api_router.include_router(billing.router)
