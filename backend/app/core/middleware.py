"""Security middleware: response hardening headers + a lightweight rate limiter.

The rate limiter is an in-process token bucket keyed by client ip (or API-key prefix).
It is adequate for a single instance and dev; a multi-instance production deployment
should move the counter to Redis. Both are config-gated.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

# Static hardening headers applied to every response.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

# Paths that serve the interactive docs UI need a relaxed CSP (Swagger/ReDoc load JS/CSS
# and connect to /openapi.json); everything else gets the strict API policy.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_DOCS_CSP = (
    "default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "connect-src 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard hardening headers + a Content-Security-Policy to every response.

    The API gets the strict `CSP_POLICY`; the docs routes get a Swagger-compatible policy
    so `/docs` still renders without weakening the JSON API's CSP."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        is_docs = request.url.path.startswith(_DOCS_PATHS)
        response.headers.setdefault(
            "Content-Security-Policy", _DOCS_CSP if is_docs else settings.CSP_POLICY
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-client rate limit (`RATE_LIMIT_PER_MINUTE`) → 429 when exceeded."""

    def __init__(self, app, limit_per_minute: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._limit = limit_per_minute
        self._window = 60.0
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "anonymous"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        now = time.monotonic()
        key = self._client_key(request)
        recent = [t for t in self._hits[key] if now - t < self._window]
        if len(recent) >= self._limit:
            self._hits[key] = recent
            return JSONResponse(
                status_code=429, content={"detail": "Rate limit exceeded. Try again shortly."}
            )
        recent.append(now)
        self._hits[key] = recent
        return await call_next(request)


def install_middleware(app) -> None:  # type: ignore[no-untyped-def]
    """Install the hardening middlewares (order: rate limit → headers → app)."""
    if settings.ENABLE_SECURITY_HEADERS:
        app.add_middleware(SecurityHeadersMiddleware)
    if settings.RATE_LIMIT_PER_MINUTE > 0:
        app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.RATE_LIMIT_PER_MINUTE)
