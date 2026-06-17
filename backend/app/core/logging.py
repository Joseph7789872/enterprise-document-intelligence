"""Structured logging and a request/trace-id middleware.

Every request is assigned (or inherits, via the ``X-Request-ID`` header) a trace id
that is stored in a ContextVar. The audit service reads this ContextVar so that audit
records can be correlated with the originating request without threading the id
through every function call.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

# Request-scoped trace id. Read by the audit service and log records.
_trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)

TRACE_HEADER = "X-Request-ID"


def get_trace_id() -> str | None:
    """Return the trace id for the current request context, if any."""
    return _trace_id_ctx.get()


def set_trace_id(trace_id: str) -> None:
    _trace_id_ctx.set(trace_id)


class _TraceIdFilter(logging.Filter):
    """Inject the current trace id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id() or "-"
        return True


# The fields a JSON log line carries. Deliberately a fixed, small set — no request bodies
# or arbitrary record attributes — so logs never leak document content or PII.
_JSON_FIELDS = ("timestamp", "level", "logger", "trace_id", "message")


class JsonFormatter(logging.Formatter):
    """Emit one structured JSON object per log line (SIEM / log-shipper friendly)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", "-"),
            "message": record.getMessage(),
        }
        return json.dumps(payload)


def configure_logging() -> None:
    """Configure root logging once at startup (text by default, JSON when requested)."""
    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] [trace=%(trace_id)s] %(message)s"
            )
        )
    handler.addFilter(_TraceIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Assign a trace id per request and echo it back in the response headers."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(TRACE_HEADER)
        trace_id = incoming or uuid.uuid4().hex
        set_trace_id(trace_id)
        response: Response = await call_next(request)
        response.headers[TRACE_HEADER] = trace_id
        return response
