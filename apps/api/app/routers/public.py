from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.paths import resolve_stored_file
from app.shares import public_daily, share_problem, token_hash
from app.store import store

router = APIRouter(prefix="/v1/public", tags=["public"])


def _open_log(token: str):
    if not token or len(token) < 20:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    digest = token_hash(token)
    log = store.daily_by_share_hash(digest)
    problem = share_problem(log, digest)
    if problem == 410:
        raise HTTPException(status_code=410, detail="Срок ссылки истёк")
    if problem is not None or log is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    return log


@router.get("/daily/{token}")
def read_public_daily(token: str):
    log = _open_log(token)
    project = store.get_project(log.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    return {"ok": True, "data": public_daily(log, project, token, store.get_user)}


@router.get("/files/{file_id}")
def read_public_file(file_id: str, t: str = ""):
    log = _open_log(t)
    photo = next((item for item in log.photos if item.public_id == file_id), None)
    stored = store.get_upload(file_id)
    if (
        photo is None
        or stored is None
        or stored.kind != "public"
        or stored.daily_log_id != log.id
    ):
        raise HTTPException(status_code=404, detail="Файл не найден")
    try:
        path = resolve_stored_file(stored.kind, stored.name)
    except ValueError:
        raise HTTPException(status_code=404, detail="Файл не найден") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path, media_type="image/jpeg")
