"""Photo punch routes. The pilot punch routes stay on the site router."""

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict

from app.company_features import require_feature, resolve_path_company
from app.idempotency import IdempotencyConflict, run_idempotent
from app.punch_photos import (
    PunchConflict,
    PunchForbidden,
    add_photo,
    build_pdf,
    create_item,
    file_for_punch,
    get_item,
    list_items,
    set_status,
    soft_delete,
)
from app.schemas import User

router = APIRouter(prefix="/v1/site", tags=["punch-photos"])


class PunchCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    location: str = ""
    trade: str = ""
    due_date: str | None = None
    assignee_id: str | None = None


class StatusBody(BaseModel):
    status: str
    row_version: int


class DeleteBody(BaseModel):
    row_version: int


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, PunchConflict):
        return HTTPException(status_code=409, detail="Изменено другим")
    if isinstance(exc, PunchForbidden):
        return HTTPException(status_code=403, detail="Недостаточно прав")
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail="Не найдено")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, IdempotencyConflict):
        return HTTPException(status_code=409, detail="Этот запрос уже отправлен с другими данными")
    raise exc


def _company(pid: str, user: User) -> str:
    """Owner company key from the same path query the feature gate uses."""
    company_id = resolve_path_company("projects", pid, user)
    if not company_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    return company_id


@router.get("/projects/{pid}/punch-items")
def list_punches(
    pid: str,
    status: str | None = None,
    assignee: str | None = None,
    overdue: str | None = None,
    mine: str | None = None,
    user: User = Depends(require_feature("punch_photos")),
):
    company_id = _company(pid, user)
    try:
        data = list_items(
            user,
            pid,
            company_id,
            status=status,
            assignee=assignee,
            overdue=overdue == "1",
            mine=mine == "1",
        )
    except (PunchConflict, PunchForbidden, LookupError, ValueError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": data}


@router.post("/projects/{pid}/punch-items")
def create_punch(
    pid: str,
    body: PunchCreate,
    user: User = Depends(require_feature("punch_photos")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    company_id = _company(pid, user)

    def create():
        return create_item(user, pid, company_id, body.model_dump())

    try:
        data = run_idempotent(user.id, idempotency_key, body.model_dump_json(), create)
    except (PunchConflict, PunchForbidden, LookupError, ValueError, IdempotencyConflict) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": data}


@router.get("/projects/{pid}/punch-items.pdf")
def punch_pdf(pid: str, user: User = Depends(require_feature("punch_photos"))):
    company_id = _company(pid, user)
    try:
        payload = build_pdf(user, pid, company_id)
    except (PunchConflict, PunchForbidden, LookupError, ValueError) as exc:
        raise _http(exc) from exc
    return Response(content=payload, media_type="application/pdf")


@router.get("/projects/{pid}/punch-items/{punch_id}")
def read_punch(pid: str, punch_id: str, user: User = Depends(require_feature("punch_photos"))):
    company_id = _company(pid, user)
    try:
        return {"ok": True, "data": get_item(user, punch_id, company_id, pid)}
    except (PunchConflict, PunchForbidden, LookupError, ValueError) as exc:
        raise _http(exc) from exc


@router.post("/projects/{pid}/punch-items/{punch_id}/status")
def punch_status(
    pid: str,
    punch_id: str,
    body: StatusBody,
    user: User = Depends(require_feature("punch_photos")),
):
    company_id = _company(pid, user)
    try:
        data = set_status(user, punch_id, company_id, pid, body.status, body.row_version)
    except (PunchConflict, PunchForbidden, LookupError, ValueError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": data}


@router.post("/projects/{pid}/punch-items/{punch_id}/photos")
async def punch_photo(
    pid: str,
    punch_id: str,
    user: User = Depends(require_feature("punch_photos")),
    phase: str = Form(...),
    row_version: int = Form(...),
    photo_id: str = Form(..., alias="id"),
    file_id: str = Form(...),
    file: UploadFile = File(...),
):
    company_id = _company(pid, user)
    raw = await file.read()
    try:
        data = add_photo(
            user,
            punch_id,
            company_id,
            pid,
            photo_id=photo_id,
            file_id=file_id,
            phase=phase,
            row_version=row_version,
            raw=raw,
        )
    except (PunchConflict, PunchForbidden, LookupError, ValueError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": data}


@router.get("/projects/{pid}/punch-items/{punch_id}/files/{file_id}")
def punch_file(
    pid: str,
    punch_id: str,
    file_id: str,
    user: User = Depends(require_feature("punch_photos")),
):
    company_id = _company(pid, user)
    try:
        path, mime = file_for_punch(punch_id, company_id, file_id, pid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Не найдено") from exc
    return FileResponse(path, media_type=mime)


@router.get("/projects/{pid}/punch-items/{punch_id}/link")
def punch_link(pid: str, punch_id: str, user: User = Depends(require_feature("punch_photos"))):
    company_id = _company(pid, user)
    try:
        get_item(user, punch_id, company_id, pid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Не найдено") from exc
    return {"ok": True, "data": {"href": f"/v1/site/projects/{pid}/punch-items/{punch_id}"}}


@router.post("/projects/{pid}/punch-items/{punch_id}/delete")
def delete_punch(
    pid: str,
    punch_id: str,
    body: DeleteBody,
    user: User = Depends(require_feature("punch_photos")),
):
    company_id = _company(pid, user)
    try:
        data = soft_delete(user, punch_id, company_id, pid, body.row_version)
    except (PunchConflict, PunchForbidden, LookupError, ValueError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": data}
