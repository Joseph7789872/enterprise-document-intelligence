"""Structured logging tests (Phase 8): JSON formatter emits only the known field set."""

from __future__ import annotations

import json
import logging

from app.core.logging import _JSON_FIELDS, JsonFormatter


def test_json_formatter_emits_only_known_fields() -> None:
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    record.trace_id = "abc123"
    payload = json.loads(JsonFormatter().format(record))
    # No request bodies / arbitrary attributes leak — exactly the documented fields.
    assert set(payload) == set(_JSON_FIELDS)
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["trace_id"] == "abc123"


def test_json_formatter_defaults_trace_id_when_absent() -> None:
    record = logging.LogRecord(
        name="app.test", level=logging.WARNING, pathname=__file__, lineno=1,
        msg="no trace", args=(), exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["trace_id"] == "-"
