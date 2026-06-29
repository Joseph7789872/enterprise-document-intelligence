"""HTML text-extraction unit tests (Phase C URL import path)."""

from __future__ import annotations

import pytest
from app.services.extraction import ExtractionError, extract_text


def test_html_strips_scripts_and_collapses_whitespace() -> None:
    html = (
        b"<html><head><style>.x{color:red}</style></head>"
        b"<body><script>var a=1;</script><h1>Veloxa</h1>"
        b"<p>Pro   is    priced\n\nat $110.</p></body></html>"
    )
    out = extract_text(html, "text/html", "page.html")
    assert "Veloxa" in out.text
    assert "Pro is priced at $110." in out.text  # whitespace collapsed
    assert "var a=1" not in out.text  # script dropped
    assert ".x{color" not in out.text  # style dropped
    assert out.page_count is None


def test_html_dispatch_by_content_type_without_extension() -> None:
    out = extract_text(b"<p>Hello world</p>", "text/html; charset=utf-8", "noext")
    assert out.text == "Hello world"


def test_empty_html_raises() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"<html><body><script>x</script></body></html>", "text/html", "p.html")
