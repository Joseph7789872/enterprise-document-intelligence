"""Observability tracing — a pluggable backend (Langfuse or a no-op fake).

The workflow wraps each node in :func:`trace_span`, records each LLM call via
:func:`record_generation`, and opens one root trace per request with
:func:`start_trace`. The active tracer comes from
``settings.effective_observability_provider`` and defaults to :class:`FakeTracer`
(structured logging only), so the app and tests run fully offline.

Privacy: spans and generations carry only **metadata** (node, model, counts, ids).
Prompt / answer / retrieved-context text is sent to an external tracer **only** when
``LANGFUSE_CAPTURE_IO`` is explicitly enabled — never by default.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_trace_id

logger = logging.getLogger("app.trace")

# The active root trace handle for the current request (provider-specific, or None).
_current_trace: ContextVar[Any | None] = ContextVar("current_trace", default=None)


class Tracer(Protocol):
    def start_trace(
        self,
        name: str,
        *,
        tenant_id: Any | None = None,
        user_id: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AbstractContextManager[None]: ...

    def span(self, name: str, **attrs: Any) -> AbstractContextManager[None]: ...

    def record_generation(self, *, node: str, model: str, **attrs: Any) -> None: ...


class FakeTracer:
    """No-op tracer: structured logging only, no external calls (offline default)."""

    @contextmanager
    def start_trace(
        self,
        name: str,
        *,
        tenant_id: Any | None = None,
        user_id: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        trace_id = get_trace_id()
        logger.info("trace.start name=%s trace=%s tenant=%s", name, trace_id, tenant_id)
        try:
            yield
        finally:
            logger.info("trace.end name=%s trace=%s", name, trace_id)

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        trace_id = get_trace_id()
        start = time.perf_counter()
        logger.info("span.start name=%s trace=%s attrs=%s", name, trace_id, attrs)
        try:
            yield
        except Exception as exc:  # noqa: BLE001 - re-raised after logging
            elapsed = (time.perf_counter() - start) * 1000
            logger.warning(
                "span.error name=%s trace=%s ms=%.1f err=%s", name, trace_id, elapsed, exc
            )
            raise
        else:
            elapsed = (time.perf_counter() - start) * 1000
            logger.info("span.end name=%s trace=%s ms=%.1f", name, trace_id, elapsed)

    def record_generation(self, *, node: str, model: str, **attrs: Any) -> None:
        logger.info("generation node=%s model=%s attrs=%s", node, model, attrs)


class LangfuseTracer:
    """Langfuse-backed tracer (the optional ``[observability]`` extra).

    Creates a root trace per request and nests spans/generations beneath it. Honors
    ``LANGFUSE_CAPTURE_IO`` — without it, no document-derived text leaves the process.
    """

    def __init__(self) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST or None,
        )
        self._capture_io = settings.LANGFUSE_CAPTURE_IO

    @contextmanager
    def start_trace(
        self,
        name: str,
        *,
        tenant_id: Any | None = None,
        user_id: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        trace = self._client.trace(
            name=name,
            id=get_trace_id(),
            user_id=str(user_id) if user_id is not None else None,
            metadata={"tenant_id": str(tenant_id) if tenant_id else None, **(metadata or {})},
        )
        token = _current_trace.set(trace)
        try:
            yield
        finally:
            _current_trace.reset(token)
            self._client.flush()

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        trace = _current_trace.get()
        span = trace.span(name=name, metadata=attrs) if trace is not None else None
        try:
            yield
        finally:
            if span is not None:
                span.end()

    def record_generation(self, *, node: str, model: str, **attrs: Any) -> None:
        trace = _current_trace.get()
        if trace is None:
            return
        # Metadata only unless IO capture is explicitly enabled.
        io = {} if self._capture_io else {"input": None, "output": None}
        trace.generation(name=node, model=model, metadata=attrs, **io)


@lru_cache
def get_tracer() -> Tracer:
    """Return the configured tracer (cached per process)."""
    if settings.effective_observability_provider == "fake":
        return FakeTracer()
    return LangfuseTracer()


# ── Module-level convenience API (stable call sites for the workflow) ───────────────
def start_trace(
    name: str,
    *,
    tenant_id: Any | None = None,
    user_id: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> AbstractContextManager[None]:
    return get_tracer().start_trace(
        name, tenant_id=tenant_id, user_id=user_id, metadata=metadata
    )


def trace_span(name: str, **attrs: Any) -> AbstractContextManager[None]:
    """Open a named span under the active trace (delegates to the current tracer)."""
    return get_tracer().span(name, **attrs)


def record_generation(*, node: str, model: str, **attrs: Any) -> None:
    """Record an LLM generation under the active trace (metadata only by default)."""
    get_tracer().record_generation(node=node, model=model, **attrs)
