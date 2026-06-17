"""Text extraction from uploaded documents.

Dispatches on content type / extension to the appropriate library. Failures raise
``ExtractionError`` so the ingestion pipeline can mark the document FAILED with a
useful message instead of crashing the worker.
"""

from __future__ import annotations

import io
from dataclasses import dataclass


class ExtractionError(Exception):
    """Raised when a document cannot be parsed / its type is unsupported."""


@dataclass(frozen=True)
class ExtractedDoc:
    text: str
    page_count: int | None


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def extract_text(data: bytes, content_type: str, filename: str) -> ExtractedDoc:
    """Extract plain text from ``data`` based on its type."""
    ext = _ext(filename)
    ct = (content_type or "").lower()

    if ext == "pdf" or "pdf" in ct:
        return _extract_pdf(data)
    if ext == "docx" or "wordprocessingml" in ct:
        return _extract_docx(data)
    if ext == "txt" or ct.startswith("text/plain"):
        return _extract_txt(data)
    if ext in {"html", "htm"} or "html" in ct:
        # Deferred to a later phase; rejected explicitly for now.
        raise ExtractionError("HTML extraction is not supported yet.")
    raise ExtractionError(f"Unsupported document type: ext={ext!r} content_type={content_type!r}")


def _extract_pdf(data: bytes) -> ExtractedDoc:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises a variety of errors on bad input
        raise ExtractionError(f"Failed to parse PDF: {exc}") from exc
    text = "\n\n".join(pages).strip()
    if not text:
        raise ExtractionError("PDF contained no extractable text (possibly scanned/image-only).")
    return ExtractedDoc(text=text, page_count=len(pages))


def _extract_docx(data: bytes) -> ExtractedDoc:
    try:
        import docx

        doc = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception as exc:
        raise ExtractionError(f"Failed to parse DOCX: {exc}") from exc
    if not text:
        raise ExtractionError("DOCX contained no extractable text.")
    return ExtractedDoc(text=text, page_count=None)


def _extract_txt(data: bytes) -> ExtractedDoc:
    for encoding in ("utf-8", "latin-1"):
        try:
            text = data.decode(encoding).strip()
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 decodes any byte string
        raise ExtractionError("Could not decode text file.")
    if not text:
        raise ExtractionError("Text file was empty.")
    return ExtractedDoc(text=text, page_count=None)
