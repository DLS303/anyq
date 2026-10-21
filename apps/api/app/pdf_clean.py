"""Remove document-info metadata from an uploaded PDF."""

from __future__ import annotations

import io
import os

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

# Override with ANYQ_MAX_PDF_PAGES. The cap is checked before pages are copied.
MAX_PDF_PAGES = 500


class PdfPageLimitError(ValueError):
    """The PDF has more pages than the configured limit."""

    def __init__(self, pages: int, limit: int):
        self.pages = pages
        self.limit = limit
        super().__init__(f"PDF page count {pages} exceeds limit {limit}")


def max_pdf_pages() -> int:
    raw = os.environ.get("ANYQ_MAX_PDF_PAGES", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    return MAX_PDF_PAGES


def strip_pdf(raw: bytes) -> bytes:
    """Return PDF bytes without Info or XMP author metadata."""
    if not raw.startswith(b"%PDF-"):
        raise ValueError("pdf")
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError("pdf")
        limit = max_pdf_pages()
        pages = len(reader.pages)
        if pages > limit:
            raise PdfPageLimitError(pages, limit)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
    except PdfReadError as exc:
        raise ValueError("pdf") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("pdf") from exc
    out = io.BytesIO()
    writer.write(out)
    cleaned = out.getvalue()
    if not cleaned.startswith(b"%PDF-"):
        raise ValueError("pdf")
    return cleaned
