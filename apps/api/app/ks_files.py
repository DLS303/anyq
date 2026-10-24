"""Signed-scan checks and storage.

The scan is parsed before the database transaction. The final name is a
server hash, written with O_EXCL after commit. Duplicate bytes are reused
inside the same company only.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from app.paths import resolve_stored_file, uploads_dir
from app.store import store

MAX_PDF = 20 * 1024 * 1024
_INFO = re.compile(
    br"/(Author|Creator|Producer|Title|Subject|Keywords|CreationDate|ModDate)\s*"
    br"(\((?:\\.|[^)\\])*\)|<[^>]*>)",
    re.IGNORECASE,
)
_ACTIVE = re.compile(br"/(JavaScript|JS|EmbeddedFile|Launch|RichMedia)(?=[\s/\[<(])", re.IGNORECASE)


class PdfRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def sanitize_pdf(raw: bytes) -> bytes:
    if not raw.startswith(b"%PDF"):
        raise PdfRejected("unsupported_type")
    if _ACTIVE.search(raw):
        raise PdfRejected("active_content")
    cleaned = _INFO.sub(b"", raw)
    if not cleaned.startswith(b"%PDF"):
        raise PdfRejected("unsupported_type")
    return cleaned


def prepare_pdf(company_id: str, raw: bytes) -> dict:
    """Sanitize and stage a temp file. Does not open the database."""
    cleaned = sanitize_pdf(raw)
    digest = hashlib.sha256(cleaned).hexdigest()
    folder = hashlib.sha256(company_id.encode()).hexdigest()
    rel = f"ks-acts/{folder}/{digest}.pdf"
    final = resolve_stored_file("upload", rel)
    final.parent.mkdir(parents=True, exist_ok=True)
    temp = final.with_name(f".{digest}.tmp")
    temp.write_bytes(cleaned)
    existing = store.get_upload_by_name(rel)
    return {
        "sha256": digest,
        "name": rel,
        "temp": temp,
        "final": final,
        "file_id": existing.id if existing else None,
        "size": len(cleaned),
    }


def publish_pdf(staged: dict, user, project_id: str, file_id: str) -> str:
    """O_EXCL publish after the database commit, then register the upload."""
    final: Path = staged["final"]
    temp: Path = staged["temp"]
    data = temp.read_bytes() if temp.is_file() else b""
    try:
        fd = os.open(final, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    temp.unlink(missing_ok=True)
    existing = store.get_upload_by_name(staged["name"])
    if existing:
        return existing.id
    item = store.add_upload(
        user,
        staged["name"],
        "application/pdf",
        project_id,
        kind="upload",
        file_id=file_id,
    )
    return item.id


def discard_temp(staged: dict | None) -> None:
    if not staged:
        return
    path: Path = staged["temp"]
    path.unlink(missing_ok=True)
    uploads_dir()
