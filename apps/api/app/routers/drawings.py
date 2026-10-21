"""Drawing upload and revision routes. Access ids are read from the path only."""

import os
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.company_features import require_feature
from app.deps import require_user
from app.drawings import (
    Access,
    DrawingConflict,
    add_revision,
    create_sheet,
    get_sheet,
    list_sheets,
    load_access,
    open_file,
    parse_uuid,
    revision_label,
)
from app.paths import discard_upload, kind_root
from app.schemas import User

router = APIRouter(prefix="/v1/site", tags=["drawings"])

_CHUNK = 1024 * 1024


def gate(request: Request, user: User = Depends(require_user)) -> Access:
    return load_access(request, user)


def _version(value: str | None) -> int | None:
    token = (value or "").strip()
    if not token:
        return None
    if not token.lstrip("-").isdigit():
        raise HTTPException(status_code=400, detail="Некорректная версия")
    return int(token)


def _limit() -> int:
    # Read the module global so tests can tighten the cap without rebinding this name.
    from app import drawings as drawings_mod

    return int(drawings_mod.MAX_PDF_BYTES)


def reject_body_length(content_length: str | None) -> None:
    """Refuse an oversized request before any upload byte is written."""
    if content_length is None or not str(content_length).strip():
        return
    try:
        size = int(str(content_length).strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный запрос") from exc
    if size > _limit():
        raise HTTPException(status_code=413, detail="Файл больше лимита")


def spool_upload(source, dest, *, limit: int | None = None, chunk: int = _CHUNK) -> None:
    """Copy the upload in chunks. Cross the cap and the temp file is removed."""
    cap = _limit() if limit is None else limit
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    total = 0
    try:
        while True:
            block = source.read(chunk)
            if not block:
                break
            total += len(block)
            if total > cap:
                raise HTTPException(status_code=413, detail="Файл больше лимита")
            view = memoryview(block)
            written = 0
            while written < len(view):
                written += os.write(fd, view[written:])
    except Exception:
        os.close(fd)
        discard_upload(dest)
        raise
    os.close(fd)


def _incoming(request: Request, upload: UploadFile) -> bytes:
    reject_body_length(request.headers.get("content-length"))
    tmp = kind_root("drawing_pdf") / f".part-{uuid4().hex}"
    try:
        spool_upload(upload.file, tmp)
        data = tmp.read_bytes()
    finally:
        discard_upload(tmp)
    if len(data) > _limit():
        raise HTTPException(status_code=413, detail="Файл больше лимита")
    return data


@router.get("/projects/{pid}/drawing-sheets")
def drawing_sheets(access: Access = Depends(gate), _: User = Depends(require_feature("drawings"))):
    return {"ok": True, "data": list_sheets(access)}


@router.post("/projects/{pid}/drawings")
def post_drawing(
    request: Request,
    access: Access = Depends(gate),
    _: User = Depends(require_feature("drawings")),
    file: UploadFile = File(...),
    id: str | None = Form(default=None),
    revision_id: str | None = Form(default=None),
    file_id: str | None = Form(default=None),
    title: str | None = Form(default=None),
    code: str | None = Form(default=None),
    rev: str | None = Form(default=None),
    set_id: str | None = Form(default=None),
    set_title: str | None = Form(default=None),
    discipline: str | None = Form(default=None),
    row_version: str | None = Form(default=None),
):
    revision_label(rev, "A")
    raw = _incoming(request, file)
    try:
        data = create_sheet(
            access,
            user_id=access.user_id,
            drawing_id=parse_uuid(id) or "",
            revision_id=parse_uuid(revision_id) or "",
            file_id=parse_uuid(file_id) or "",
            raw=raw,
            title=title,
            code=code,
            rev=rev,
            set_id=parse_uuid(set_id, required=False),
            set_title=set_title,
            discipline=discipline,
            row_version=_version(row_version),
        )
    except DrawingConflict as exc:
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    return {"ok": True, "data": data}


@router.get("/drawings/{did}")
def read_drawing(did: str, rev: str | None = None, access: Access = Depends(gate)):
    return {"ok": True, "data": get_sheet(access, did, rev)}


@router.get("/drawings/{did}/file")
def read_drawing_file(did: str, rev: str | None = None, access: Access = Depends(gate)):
    path = open_file(access, did, rev)
    return FileResponse(path, media_type="application/pdf", filename="sheet.pdf")


@router.post("/drawings/{did}/revisions")
def post_revision(
    did: str,
    request: Request,
    access: Access = Depends(gate),
    file: UploadFile = File(...),
    id: str | None = Form(default=None),
    file_id: str | None = Form(default=None),
    rev: str | None = Form(default=None),
    row_version: str | None = Form(default=None),
):
    if (rev or "").strip():
        revision_label(rev, "A")
    raw = _incoming(request, file)
    try:
        data = add_revision(
            access,
            did,
            user_id=access.user_id,
            revision_id=parse_uuid(id) or "",
            file_id=parse_uuid(file_id) or "",
            raw=raw,
            rev=rev,
            row_version=_version(row_version),
        )
    except DrawingConflict as exc:
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    return {"ok": True, "data": data}
