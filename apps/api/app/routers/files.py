from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.deps import require_user
from app.paths import resolve_stored_file
from app.schemas import User
from app.store import store

router = APIRouter(tags=["files"])


def _send(user: User, file_id: str | None = None, name: str | None = None) -> FileResponse:
    item = store.get_upload(file_id) if file_id else store.get_upload_by_name(name or "")
    if not item:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if not store.can_access_upload(user, item):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    try:
        path = resolve_stored_file(item.kind, item.name)
    except ValueError:
        raise HTTPException(status_code=404, detail="Файл не найден") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path, media_type=item.content_type)


@router.get("/v1/files/{file_id}")
def read_file(file_id: str, user: User = Depends(require_user)):
    return _send(user, file_id=file_id)


@router.get("/uploads/{name}")
def read_legacy_upload(name: str, user: User = Depends(require_user)):
    safe = Path(name).name
    if safe != name or not safe:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return _send(user, name=safe)
