"""Text extraction tests for TXT, DOCX, PDF (+ unsupported types)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.extraction import ExtractionError, extract_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_txt() -> None:
    data = (FIXTURES / "sample.txt").read_bytes()
    result = extract_text(data, "text/plain", "sample.txt")
    assert "Acme Corporation" in result.text
    assert result.page_count is None


def test_extract_docx() -> None:
    data = (FIXTURES / "sample.docx").read_bytes()
    result = extract_text(
        data,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "sample.docx",
    )
    assert "vacation" in result.text


def test_extract_pdf() -> None:
    data = (FIXTURES / "sample.pdf").read_bytes()
    result = extract_text(data, "application/pdf", "sample.pdf")
    assert "Employee Handbook" in result.text
    assert result.page_count == 1


def test_unsupported_type_raises() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"<svg></svg>", "image/svg+xml", "drawing.svg")


def test_html_is_explicitly_unsupported() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"<html></html>", "text/html", "page.html")


def test_empty_txt_raises() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"   ", "text/plain", "blank.txt")
