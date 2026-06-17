"""Aggregate v1 API routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, audit, auth, compliance, documents, evals, health, query, search

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(query.router)
api_router.include_router(evals.router)
api_router.include_router(admin.router)
api_router.include_router(compliance.router)
