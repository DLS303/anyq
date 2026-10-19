"""Drawing upload and revision routes. Access ids are read from the path only."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.deps import require_user
from app.drawings import (
    MAX_PDF_BYTES,
    Access,
    DrawingConflict,
    add_revision,
    create_sheet,
    get_sheet,
    list_sheets,
    load_access,
    open_file,
    parse_uuid,
)
from app.schemas import User

router = APIRouter(prefix="/v1/site", tags=["drawings"])


def gate(request: Request, user: User = Depends(require_user)) -> Access:
    return load_access(request, user.id)


def _version(value: str | None) -> int | None:
    token = (value or "").strip()
    if not token:
        return None
    if not token.lstrip("-").isdigit():
        raise HTTPException(status_code=400, detail="Некорректная версия")
    return int(token)


def _bytes(upload: UploadFile) -> bytes:
    return upload.file.read(MAX_PDF_BYTES + 1)


@router.get("/projects/{pid}/drawing-sheets")
def drawing_sheets(access: Access = Depends(gate)):
    return {"ok": True, "data": list_sheets(access)}


@router.post("/projects/{pid}/drawings")
def post_drawing(
    access: Access = Depends(gate),
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
    try:
        data = create_sheet(
            access,
            user_id=access.user_id,
            drawing_id=parse_uuid(id) or "",
            revision_id=parse_uuid(revision_id) or "",
            file_id=parse_uuid(file_id) or "",
            raw=_bytes(file),
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
    access: Access = Depends(gate),
    file: UploadFile = File(...),
    id: str | None = Form(default=None),
    file_id: str | None = Form(default=None),
    rev: str | None = Form(default=None),
    row_version: str | None = Form(default=None),
):
    try:
        data = add_revision(
            access,
            did,
            user_id=access.user_id,
            revision_id=parse_uuid(id) or "",
            file_id=parse_uuid(file_id) or "",
            raw=_bytes(file),
            rev=rev,
            row_version=_version(row_version),
        )
    except DrawingConflict as exc:
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    return {"ok": True, "data": data}
