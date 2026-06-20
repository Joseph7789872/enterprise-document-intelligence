"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import TraceIdMiddleware, configure_logging
from app.core.middleware import install_middleware
from app.errors import register_exception_handlers
from app.version import __version__

_DESCRIPTION = """\
**Sales-enablement assistant for Account Executives** — ask natural-language questions
of your team's sales playbooks (product, pricing, ICP, discovery/demo scripts,
competitive battlecards, case studies) and get fast, cited, grounded answers.

Two jobs: **new-rep ramp** (curated starter questions) and **live objection prep**
(a saved objection library). Managers upload and curate content and control which
content is rep-visible vs. manager-only; AEs consume via chat.

**Auth**: register a tenant (`POST /auth/register`) to create the manager account, then
`POST /auth/login` for a bearer token. Send it as `Authorization: Bearer <token>`.
"""

# One description per router tag (the routers already set matching `tags=[...]`).
_OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "auth", "description": "Tenant registration, login, token refresh, current user."},
    {
        "name": "documents",
        "description": "Upload, list, fetch, delete sales content/playbooks (manager-managed).",
    },
    {
        "name": "search",
        "description": "Hybrid (vector + BM25) re-ranked, visibility-filtered content search.",
    },
    {
        "name": "query",
        "description": "Multi-agent cited Q&A with streaming (the AE chat).",
    },
    {"name": "ramp", "description": "Manager-curated new-rep ramp checklist (AE-readable)."},
    {
        "name": "objections",
        "description": "Manager-curated objection library for objection-lookup quick mode.",
    },
    {"name": "evals", "description": "RAGAS evaluation run history (admin, read-only)."},
    {
        "name": "admin",
        "description": "Rep (user) management, groups, and tenant settings (manager/admin).",
    },
    {
        "name": "compliance",
        "description": "Compliance config, retention policy, GDPR DSRs (enterprise; flag-gated).",
    },
    {"name": "audit", "description": "Audit-log query and SIEM-ready export (manager/admin)."},
]


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Sales Assistant",
        version=__version__,
        description=_DESCRIPTION,
        openapi_tags=_OPENAPI_TAGS,
        contact={"name": "Sales Assistant Support", "email": "support@example.com"},
        license_info={"name": "Proprietary"},
        servers=[{"url": "/", "description": "This deployment"}],
    )

    # Middleware executes in reverse registration order, so register inner-to-outer:
    # security headers + rate limiting first, then CORS, then trace id outermost (so the
    # trace id is set before anything else runs and is available to audit/logging).
    install_middleware(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TraceIdMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
