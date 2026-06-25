"""Aggregate v1 API routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    audit,
    auth,
    compliance,
    documents,
    evals,
    health,
    objections,
    query,
    ramp,
    search,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(query.router)
api_router.include_router(admin.router)
# V1 sales: manager-curated ramp checklist + objection library (AE-readable).
api_router.include_router(ramp.router)
api_router.include_router(objections.router)

# Enterprise-only surfaces — mounted only when their v1 feature flag is on (off in the
# production sales product; on in dev/test so the suite still covers them).
if settings.ENABLE_EVALS:
    api_router.include_router(evals.router)
if settings.ENABLE_COMPLIANCE:
    api_router.include_router(compliance.router)
