"""Material approvals. Flag off, or no project membership, is 404."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from app.company_features import require_feature
from app.idempotency import IdempotencyConflict, run_idempotent
from app.schemas import User
from app.store_procurement import request_from_approval
from app.submittal_service import (
    attach_file,
    create_approval,
    create_link,
    list_for_user,
    mark_mismatch,
    new_version,
    project_id_of,
    public_decide,
    public_read,
    read_file,
    read_for_user,
    render_pdf,
    revoke_link,
    set_price,
    set_status,
    tombstone,
)

router = APIRouter(prefix="/v1/site", tags=["submittals"])
public = APIRouter(prefix="/v1/public", tags=["submittals"])

_PUBLIC_HEADERS = {
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class SpecIn(BaseModel):
    param: str = ""
    value: str = ""


class AnalogIn(BaseModel):
    brand: str = ""
    manufacturer: str = ""


class SupplierIn(BaseModel):
    name: str = ""


class CreateIn(BaseModel):
    id: str = ""
    name: str = ""
    brand: str = ""
    manufacturer: str = ""
    unit: str = ""
    qty: float | None = None
    need_by: str | None = None
    request_item_id: str | None = None
    specs: list[SpecIn] = Field(default_factory=list)
    analogs: list[AnalogIn] = Field(default_factory=list)
    suppliers: list[SupplierIn | str] = Field(default_factory=list)
    approver_ids: list[str] = Field(default_factory=list)
    indicative_price: float | None = None
    price_file_id: str | None = None
    row_version: int | None = None


class StatusIn(BaseModel):
    status: str
    comment: str = ""
    row_version: int


class VersionIn(BaseModel):
    id: str
    row_version: int


class DeleteIn(BaseModel):
    row_version: int


class LinkIn(BaseModel):
    id: str
    expires_in_days: int = 14


class PriceIn(BaseModel):
    price: float
    file_id: str
    row_version: int


class MismatchIn(BaseModel):
    brand: str
    row_version: int


class PublicDecisionIn(BaseModel):
    decision: str
    comment: str = ""


def _access(request: Request) -> dict:
    company_id = str(getattr(request.state, "feature_company_id", "") or "")
    pid = str(request.path_params.get("pid") or "")
    sid = str(request.path_params.get("sid") or "")
    if sid:
        real = project_id_of(sid)
        if not real or (pid and pid != real):
            raise HTTPException(status_code=404, detail="Не найдено")
        pid = real
    if not company_id or not pid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"project_id": pid, "company_id": company_id, "entity_id": sid or None}


def _public_body(data: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data}, status_code=status_code, headers=_PUBLIC_HEADERS)


@router.get("/projects/{pid}/material-approvals")
def list_items(pid: str, request: Request, user: User = Depends(require_feature("submittals"))):
    access = _access(request)
    if access["project_id"] != pid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": list_for_user(user, pid)}


@router.post("/projects/{pid}/material-approvals")
def add_item(
    pid: str,
    body: CreateIn,
    request: Request,
    user: User = Depends(require_feature("submittals")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    access = _access(request)
    if access["project_id"] != pid:
        raise HTTPException(status_code=404, detail="Не найдено")
    payload = body.model_dump()
    payload["suppliers"] = [
        item.get("name", "") if isinstance(item, dict) else item for item in payload.get("suppliers") or []
    ]

    def create():
        return create_approval(user, access, payload)

    try:
        data = run_idempotent(user.id, idempotency_key, body.model_dump_json(), create)
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="Этот запрос уже отправлен с другими данными") from exc
    return {"ok": True, "data": data}


@router.get("/material-approvals/{sid}")
def read_item(sid: str, request: Request, user: User = Depends(require_feature("submittals"))):
    access = _access(request)
    if access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": read_for_user(user, sid)}


@router.post("/material-approvals/{sid}/status")
def post_status(sid: str, body: StatusIn, request: Request, user: User = Depends(require_feature("submittals"))):
    access = _access(request)
    if access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": set_status(user, sid, body.status, body.row_version, body.comment)}


@router.post("/material-approvals/{sid}/version")
def post_version(sid: str, body: VersionIn, request: Request, user: User = Depends(require_feature("submittals"))):
    access = _access(request)
    if access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": new_version(user, sid, body.model_dump())}


@router.post("/material-approvals/{sid}/delete")
def post_delete(sid: str, body: DeleteIn, request: Request, user: User = Depends(require_feature("submittals"))):
    access = _access(request)
    if access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": tombstone(user, sid, body.row_version)}


@router.post("/projects/{pid}/material-approvals/{sid}/files")
async def post_file(
    pid: str,
    sid: str,
    request: Request,
    user: User = Depends(require_feature("submittals")),
    file: UploadFile = File(...),
    file_id: str = Form(..., alias="id"),
    row_version: int = Form(...),
    kind: str = Form(default="cert"),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    raw = await file.read()
    data = attach_file(user, access, sid, file_id, raw, file.content_type, row_version, kind)
    return {"ok": True, "data": data}


@router.get("/projects/{pid}/material-approvals/{sid}/files/{file_id}")
def get_file(
    pid: str,
    sid: str,
    file_id: str,
    request: Request,
    user: User = Depends(require_feature("submittals")),
):
    del user
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    path, media_type = read_file(pid, sid, file_id)
    return FileResponse(path, media_type=media_type)


@router.post("/projects/{pid}/material-approvals/{sid}/link")
def post_link(
    pid: str,
    sid: str,
    body: LinkIn,
    request: Request,
    user: User = Depends(require_feature("submittals")),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": create_link(user, access, sid, body.model_dump())}


@router.post("/projects/{pid}/material-approvals/{sid}/links/{link_id}/revoke")
def post_revoke(
    pid: str,
    sid: str,
    link_id: str,
    request: Request,
    user: User = Depends(require_feature("submittals")),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": revoke_link(user, access, sid, link_id)}


@router.post("/projects/{pid}/material-approvals/{sid}/price")
def post_price(
    pid: str,
    sid: str,
    body: PriceIn,
    request: Request,
    user: User = Depends(require_feature("submittals")),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": set_price(user, sid, body.price, body.file_id, body.row_version)}


@router.post("/projects/{pid}/material-approvals/{sid}/to-request")
def post_to_request(
    pid: str,
    sid: str,
    request: Request,
    user: User = Depends(require_feature("submittals")),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    data = read_for_user(user, sid)
    if data["project_id"] != pid or data["status"] not in {"approved", "approved_with_note"}:
        raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
    from app.store import store

    project = store.get_project(pid)
    if project is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    created = request_from_approval(store, project, user, data)
    return {"ok": True, "data": created}


@router.post("/projects/{pid}/material-approvals/{sid}/mismatch")
def post_mismatch(
    pid: str,
    sid: str,
    body: MismatchIn,
    request: Request,
    user: User = Depends(require_feature("submittals")),
):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"ok": True, "data": mark_mismatch(user, sid, body.brand, body.row_version)}


@router.get("/projects/{pid}/material-approvals/{sid}/pdf")
def get_pdf(pid: str, sid: str, request: Request, user: User = Depends(require_feature("submittals"))):
    access = _access(request)
    if access["project_id"] != pid or access["entity_id"] != sid:
        raise HTTPException(status_code=404, detail="Не найдено")
    payload = render_pdf(user, sid)
    return Response(content=payload, media_type="application/pdf", headers={"Referrer-Policy": "no-referrer"})


@public.get("/material/{token}")
def read_public_material(token: str):
    return _public_body(public_read(token))


@public.post("/material/{token}")
def decide_public_material(token: str, body: PublicDecisionIn):
    return _public_body(public_decide(token, body.decision, body.comment))
