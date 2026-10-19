"""Designer questions. Flag off, or no project membership, is 404."""

from __future__ import annotations

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.company_features import require_feature
from app.idempotency import IdempotencyConflict, run_idempotent
from app.media import MAX_UPLOAD_BYTES
from app.ratelimit import PublicRateLimited, public_rfi_limiter
from app.rfi_service import (
    answer_rfi,
    attach_file,
    create_link,
    create_rfi,
    list_for_user,
    public_answer,
    public_file,
    public_read,
    read_file,
    read_for_user,
    render_pdf,
    revoke_link,
    set_status,
    tombstone,
)
from app.schemas import User

router = APIRouter(prefix="/v1/site", tags=["rfi"])
public = APIRouter(prefix="/v1/public", tags=["rfi"])


class ContactIn(BaseModel):
    id: str
    full_name: str = ""
    phone: str = ""
    email: str = ""
    organization: str = ""


class RfiCreate(BaseModel):
    id: str = ""
    question: str = ""
    title: str = ""
    due_date: str | None = None
    assignee_user_id: str | None = None
    drawing_revision_id: str | None = None
    contact: ContactIn | None = None
    row_version: int | None = None


class AnswerIn(BaseModel):
    answer: str
    row_version: int


class StatusIn(BaseModel):
    status: str
    row_version: int


class DeleteIn(BaseModel):
    row_version: int


class LinkIn(BaseModel):
    id: str
    expires_in_days: int = 14


class PublicAnswerIn(BaseModel):
    answer: str


_CHUNK = 64 * 1024


def _limit_public(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        public_rfi_limiter.check(host)
    except PublicRateLimited as exc:
        raise HTTPException(status_code=429, detail="Слишком много запросов") from exc


async def _read_capped(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        block = await upload.read(_CHUNK)
        if not block:
            break
        total += len(block)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Файл больше 10 МБ")
        chunks.append(block)
    return b"".join(chunks)


def _file_response(path: str, media_type: str) -> FileResponse:
    return FileResponse(
        path,
        media_type=media_type,
        filename=Path(path).name,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _without_contact(data: dict) -> dict:
    return {key: value for key, value in data.items() if key != "contact"}


def _access(request: Request) -> dict:
    company_id = str(getattr(request.state, "feature_company_id", "") or "")
    pid = str(request.path_params.get("pid") or "")
    rid = str(request.path_params.get("rid") or "")
    if rid:
        from app.rfi_service import project_id_of

        real = project_id_of(rid)
        if not real or (pid and pid != real):
            raise HTTPException(status_code=404, detail="Не найдено")
        pid = real
    if not company_id or not pid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"project_id": pid, "company_id": company_id, "entity_id": rid or None}


@router.get("/projects/{pid}/rfis")
def list_rfis(pid: str, request: Request, user: User = Depends(require_feature("rfi"))):
    access = _access(request)
    if access["project_id"] != pid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": list_for_user(user, pid)}


@router.post("/projects/{pid}/rfis")
def add_rfi(
    pid: str,
    body: RfiCreate,
    request: Request,
    user: User = Depends(require_feature("rfi")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    access = _access(request)
    if access["project_id"] != pid:
        raise HTTPException(status_code=404, detail="Не найдено")

    def create():
        return create_rfi(user, access, body.model_dump())

    try:
        data = run_idempotent(
            user.id,
            idempotency_key,
            body.model_dump_json(),
            create,
            persist=_without_contact,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=409, detail="Этот запрос уже отправлен с другими данными"
        ) from exc
    return {"ok": True, "data": data}


@router.get("/rfis/{rid}")
def read_rfi(rid: str, request: Request, user: User = Depends(require_feature("rfi"))):
    access = _access(request)
    if access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": read_for_user(user, rid)}


@router.post("/rfis/{rid}/answer")
def post_answer(
    rid: str,
    body: AnswerIn,
    request: Request,
    user: User = Depends(require_feature("rfi")),
):
    access = _access(request)
    if access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": answer_rfi(user, rid, body.answer, body.row_version)}


@router.post("/rfis/{rid}/status")
def post_status(
    rid: str,
    body: StatusIn,
    request: Request,
    user: User = Depends(require_feature("rfi")),
):
    access = _access(request)
    if access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": set_status(user, rid, body.status, body.row_version)}


@router.post("/rfis/{rid}/delete")
def post_delete(
    rid: str,
    body: DeleteIn,
    request: Request,
    user: User = Depends(require_feature("rfi")),
):
    access = _access(request)
    if access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": tombstone(user, rid, body.row_version)}


@router.post("/projects/{pid}/rfis/{rid}/files")
async def post_file(
    pid: str,
    rid: str,
    request: Request,
    user: User = Depends(require_feature("rfi")),
    file: UploadFile = File(...),
    file_id: str = Form(..., alias="id"),
    row_version: int = Form(...),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    raw = await _read_capped(file)
    try:
        data = attach_file(
            user, access, rid, file_id, raw, file.content_type, row_version
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": data}


@router.get("/projects/{pid}/rfis/{rid}/files/{file_id}")
def get_file(
    pid: str,
    rid: str,
    file_id: str,
    request: Request,
    user: User = Depends(require_feature("rfi")),
):
    del user
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    path, media_type = read_file(pid, rid, file_id)
    return _file_response(path, media_type)


@router.post("/projects/{pid}/rfis/{rid}/link")
def post_link(
    pid: str,
    rid: str,
    body: LinkIn,
    request: Request,
    user: User = Depends(require_feature("rfi")),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": create_link(user, access, rid, body.model_dump())}


@router.post("/projects/{pid}/rfis/{rid}/link/revoke")
def post_revoke(
    pid: str,
    rid: str,
    body: LinkIn,
    request: Request,
    user: User = Depends(require_feature("rfi")),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": revoke_link(user, access, rid, body.id)}


@router.get("/projects/{pid}/rfis/{rid}/pdf")
def get_pdf(
    pid: str, rid: str, request: Request, user: User = Depends(require_feature("rfi"))
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != rid:
        raise HTTPException(status_code=404, detail="Не найдено")
    payload = render_pdf(user, rid)
    return Response(content=payload, media_type="application/pdf")


@public.get("/rfi/{token}")
def read_public_rfi(token: str, _limited: None = Depends(_limit_public)):
    return {"ok": True, "data": public_read(token)}


@public.post("/rfi/{token}")
def answer_public_rfi(
    token: str, body: PublicAnswerIn, _limited: None = Depends(_limit_public)
):
    return {"ok": True, "data": public_answer(token, body.answer)}


@public.get("/rfi/{token}/files/{file_id}")
def read_public_rfi_file(
    token: str, file_id: str, _limited: None = Depends(_limit_public)
):
    path, media_type = public_file(token, file_id)
    return _file_response(path, media_type)
