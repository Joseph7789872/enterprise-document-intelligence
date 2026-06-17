"""Tracing provider tests (FakeTracer default, safe no-ops, metadata-only)."""

from __future__ import annotations

import uuid

from app.observability import tracing
from app.observability.tracing import (
    FakeTracer,
    get_tracer,
    record_generation,
    start_trace,
    trace_span,
)


def test_get_tracer_is_fake_in_dev() -> None:
    # No langfuse extra / keys in the test env → fake tracer.
    get_tracer.cache_clear()
    assert isinstance(get_tracer(), FakeTracer)


def test_start_trace_and_span_are_safe_noops() -> None:
    tid = uuid.uuid4()
    with start_trace("query", tenant_id=tid, user_id=uuid.uuid4()):
        with trace_span("planner", subqueries=2):
            pass
        # Generations are recorded without raising even with no real backend.
        record_generation(node="planner", model="claude-sonnet-4-6", subqueries=2)


def test_span_reraises_but_logs() -> None:
    raised = False
    try:
        with trace_span("boom"):
            raise ValueError("x")
    except ValueError:
        raised = True
    assert raised


def test_fake_record_generation_omits_io() -> None:
    # The FakeTracer only logs metadata; no IO is captured or stored anywhere.
    tracer = FakeTracer()
    tracer.record_generation(node="synthesizer", model="m", confidence=0.9)  # no raise
    assert tracing.settings.LANGFUSE_CAPTURE_IO is False
