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
Secure, multi-tenant **Enterprise Document Intelligence Platform** — query private
company documents in natural language with cited, grounded answers.

**Security-first**: envelope encryption at rest, document-level ACLs enforced at
retrieval time, an append-only audit trail on every access, and classification-aware
routing of confidential documents to self-hosted models.

**Auth**: register a tenant (`POST /auth/register`), then `POST /auth/login` to obtain a
bearer token. Send it as `Authorization: Bearer <token>` on every other request.
"""

# One description per router tag (the routers already set matching `tags=[...]`).
_OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "auth", "description": "Tenant registration, login, token refresh, current user."},
    {
        "name": "documents",
        "description": "Upload, list, fetch, delete documents and manage their ACLs.",
    },
    {
        "name": "search",
        "description": "Hybrid (vector + BM25) re-ranked, ACL-filtered chunk search.",
    },
    {
        "name": "query",
        "description": "Multi-agent cited Q&A, streaming, and human-approval review.",
    },
    {"name": "evals", "description": "RAGAS evaluation run history (admin, read-only)."},
    {
        "name": "admin",
        "description": "User, group, API-key, and tenant-policy management (OWNER/ADMIN).",
    },
    {
        "name": "compliance",
        "description": "Compliance config, retention policy, and GDPR data-subject requests.",
    },
    {"name": "audit", "description": "Audit-log query and SIEM-ready export (OWNER/ADMIN)."},
]


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Enterprise Document Intelligence Platform",
        version=__version__,
        description=_DESCRIPTION,
        openapi_tags=_OPENAPI_TAGS,
        contact={"name": "EDIP Support", "email": "support@example.com"},
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
