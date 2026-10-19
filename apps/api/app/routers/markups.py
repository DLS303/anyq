"""Markup routes. The revision id is taken from the path only."""

import json
from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException, MultiPartParser

from app.company_features import require_feature
from app.deps import require_user
from app.markups import (
    MarkupAccess,
    MarkupConflict,
    _version,
    delete_markup,
    list_for,
    load_access,
    open_file,
    save_markup,
)
from app.media import MAX_UPLOAD_BYTES
from app.schemas import User

router = APIRouter(prefix="/v1/site", tags=["markups"])


def gate(request: Request, user: User = Depends(require_user)) -> MarkupAccess:
    revision_id = str(request.path_params.get("id") or "").strip()
    if not revision_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    return load_access(revision_id, user)


class _LimitedParser(MultiPartParser):
    """Stop reading the request stream once the file part passes the upload limit."""

    def __init__(self, headers: Headers, stream, **kwargs) -> None:
        super().__init__(headers, stream, **kwargs)
        self._file_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._file_bytes += end - start
            if self._file_bytes > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Файл больше лимита")
        super().on_part_data(data, start, end)


async def _form_parts(headers: Headers, stream):
    parser = _LimitedParser(headers, stream, max_files=1, max_fields=4, max_part_size=1024 * 1024)
    try:
        return await parser.parse()
    except HTTPException:
        raise
    except MultiPartException as exc:
        raise HTTPException(status_code=400, detail="Некорректные данные") from exc


async def _payload(request: Request) -> tuple[dict, bytes | None]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        async with aclosing(request.stream()) as stream:
            form = await _form_parts(request.headers, stream)
        raw_payload = form.get("payload")
        if not isinstance(raw_payload, str) or not raw_payload.strip():
            raise HTTPException(status_code=400, detail="Некорректные данные")
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Некорректные данные") from exc
        upload = form.get("file")
        raw = await upload.read() if upload is not None and hasattr(upload, "read") else None
        if hasattr(upload, "close"):
            await upload.close()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Некорректные данные")
        return payload, raw or None
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Некорректные данные") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Некорректные данные")
    return payload, None


@router.get("/revisions/{id}/markups")
def get_markups(access: MarkupAccess = Depends(gate), _: User = Depends(require_feature("drawings"))):
    return {"ok": True, "data": list_for(access)}


@router.post("/revisions/{id}/markups")
async def post_markup(
    request: Request,
    access: MarkupAccess = Depends(gate),
    _: User = Depends(require_feature("drawings")),
):
    payload, raw = await _payload(request)
    try:
        data = save_markup(access, payload, raw)
    except MarkupConflict as exc:
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    return {"ok": True, "data": data}


@router.delete("/revisions/{id}/markups/{markup_id}")
def remove_markup(
    markup_id: str,
    request: Request,
    access: MarkupAccess = Depends(gate),
    _: User = Depends(require_feature("drawings")),
):
    raw_version = request.query_params.get("row_version")
    if raw_version is None:
        raise HTTPException(status_code=400, detail="Некорректная версия")
    try:
        data = delete_markup(access, markup_id, _version(raw_version))
    except MarkupConflict as exc:
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    return {"ok": True, "data": data}


@router.get("/revisions/{id}/markups/files/{file_id}")
def get_markup_file(
    file_id: str,
    access: MarkupAccess = Depends(gate),
    _: User = Depends(require_feature("drawings")),
):
    path, mime, filename = open_file(access, file_id)
    return FileResponse(path, media_type=mime, filename=filename)
