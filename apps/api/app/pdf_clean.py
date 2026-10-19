"""Remove document-info metadata from an uploaded PDF."""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError


def strip_pdf(raw: bytes) -> bytes:
    """Return PDF bytes without Info or XMP author metadata."""
    if not raw.startswith(b"%PDF-"):
        raise ValueError("pdf")
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError("pdf")
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
