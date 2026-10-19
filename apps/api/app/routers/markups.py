"""Markup routes. The revision id is taken from the path only."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.company_features import require_feature
from app.deps import require_user
from app.markups import MarkupAccess, MarkupConflict, list_for, load_access, open_file, save_markup
from app.schemas import User

router = APIRouter(prefix="/v1/site", tags=["markups"])


def gate(request: Request, user: User = Depends(require_user)) -> MarkupAccess:
    revision_id = str(request.path_params.get("id") or "").strip()
    if not revision_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    return load_access(revision_id, user)


async def _payload(request: Request) -> tuple[dict, bytes | None]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_payload = form.get("payload")
        if not isinstance(raw_payload, str) or not raw_payload.strip():
            raise HTTPException(status_code=400, detail="Некорректные данные")
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Некорректные данные") from exc
        upload = form.get("file")
        raw = await upload.read() if upload is not None and hasattr(upload, "read") else None
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


@router.get("/revisions/{id}/markups/files/{file_id}")
def get_markup_file(
    file_id: str,
    access: MarkupAccess = Depends(gate),
    _: User = Depends(require_feature("drawings")),
):
    path, mime = open_file(access, file_id)
    return FileResponse(path, media_type=mime, filename="photo.jpg")
