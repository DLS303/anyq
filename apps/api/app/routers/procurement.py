"""Procurement requests, statement import, offers, and the competitive sheet."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.config import settings
from app.deps import require_user
from app.idempotency import IdempotencyConflict, run_idempotent
from app.paths import uploads_dir
from app.procurement_xlsx import (
    comparison_workbook,
    offers_template,
    parse_offers,
    parse_statement,
)
from app.schemas import User
from app.store import store
from app.store_budget import company_savings, project_savings, savings_for_request
from app.store_procurement import (
    access_flags,
    add_document,
    add_offer,
    apply_lines,
    apply_offers,
    create_request,
    delete_offer,
    list_requests,
    material_picker,
    member_anywhere,
    patch_document,
    patch_line,
    patch_offer,
    preview_lines,
    preview_offers,
    quick_request,
    repeat_request,
    select_best,
    select_offer,
    sheet_for,
    supplier_can_bid,
    supplier_inbox,
)

router = APIRouter(prefix="/v1/procurement", tags=["procurement"])

MAX_XLSX = 5 * 1024 * 1024
MAX_DOC = 10 * 1024 * 1024
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class RequestIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class QuickIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=40)
    qty: float = Field(gt=0)


class OfferIn(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=200)
    price_kzt: float = Field(gt=0)
    vat_included: bool | None = None
    qty_available: float | None = Field(default=None, ge=0)
    delivery_term: str = ""
    note: str = ""
    confirmed: bool = True
    source_label: str = ""
    source_doc_id: str | None = None
    offer_date: str = ""
    offered_brand: str = ""


class OfferPatch(BaseModel):
    supplier_name: str | None = None
    price_kzt: float | None = Field(default=None, gt=0)
    vat_included: bool | None = None
    qty_available: float | None = None
    delivery_term: str | None = None
    note: str | None = None
    confirmed: bool | None = None
    source_label: str | None = None
    source_doc_id: str | None = None
    offer_date: str | None = None


class LinePatch(BaseModel):
    qty: float | None = Field(default=None, gt=0)
    note: str | None = None
    title: str | None = None
    unit: str | None = None
    reference_price_kzt: float | None = None
    reference_vat_included: bool | None = None
    reference_source: str | None = None
    requires_approval: bool | None = None
    approval_id: str | None = None
    brand: str | None = None


class SelectIn(BaseModel):
    offer_id: str | None = None


class DocPatch(BaseModel):
    is_actual: bool


def _fail(exc: Exception) -> None:
    from app.submittal_service import StatusConflict

    if isinstance(exc, StatusConflict):
        raise HTTPException(409, "Этот переход статуса недоступен") from exc
    if isinstance(exc, IdempotencyConflict):
        raise HTTPException(409, "Этот запрос уже отправлен с другими данными") from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc) or "Недостаточно прав") from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc) or "Не найдено") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise exc


def _run(fn):
    from app.submittal_service import StatusConflict

    try:
        return fn()
    except (IdempotencyConflict, PermissionError, LookupError, ValueError, StatusConflict) as exc:
        _fail(exc)


def _idem(user: User, key: str | None, fingerprint: str, fn):
    from app.submittal_service import StatusConflict

    try:
        return run_idempotent(user.id, key, fingerprint, fn)
    except (IdempotencyConflict, PermissionError, LookupError, ValueError, StatusConflict) as exc:
        _fail(exc)


def _project(pid: str):
    project = store.get_project(pid)
    if not project:
        raise HTTPException(404, "Проект не найден")
    return project


def _member_project(user: User, pid: str):
    project = _project(pid)
    if not store.can_access_project(user, project):
        raise HTTPException(403, "Недостаточно прав")
    return project


def _request(user: User, rid: str):
    req = store.proc_requests.get(rid)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    project = store.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    if not store.can_access_project(user, project):
        raise HTTPException(403, "Недостаточно прав")
    return req, project


def _need(flags: dict, key: str) -> None:
    if not flags.get(key):
        raise HTTPException(403, "Недостаточно прав")


def _line(user: User, lid: str):
    line = store.proc_lines.get(lid)
    if not line:
        raise HTTPException(404, "Позиция не найдена")
    req, project = _request(user, line.request_id)
    return line, req, project


def _line_for_offer(user: User, lid: str):
    line = store.proc_lines.get(lid)
    if not line:
        raise HTTPException(404, "Позиция не найдена")
    req = store.proc_requests.get(line.request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    project = store.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    if store.can_access_project(user, project):
        return line, req, project, False
    if supplier_can_bid(user, req):
        return line, req, project, True
    raise HTTPException(403, "Недостаточно прав")


def _offer(user: User, oid: str):
    offer = store.proc_offers.get(oid)
    if not offer:
        raise HTTPException(404, "Предложение не найдено")
    line = store.proc_lines.get(offer.line_id)
    if not line:
        raise HTTPException(404, "Позиция не найдена")
    req, project = _request(user, line.request_id)
    return offer, line, req, project


def _doc(user: User, did: str):
    doc = store.proc_docs.get(did)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    req, project = _request(user, doc.request_id)
    return doc, req, project


async def _bytes(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "Файл слишком большой")
    if not data:
        raise HTTPException(400, "Пустой файл")
    return data


def _sniff_doc(data: bytes) -> tuple[str, str]:
    if data.startswith(b"%PDF"):
        return "application/pdf", ".pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise HTTPException(400, "Нужен PDF, JPEG, PNG или WEBP")


def _doc_path(project_id: str, stored_name: str):
    if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
        raise HTTPException(404, "Документ не найден")
    if not stored_name or "/" in stored_name or "\\" in stored_name or ".." in stored_name:
        raise HTTPException(404, "Документ не найден")
    root = (uploads_dir() / project_id / "proc").resolve()
    path = (root / stored_name).resolve()
    if root not in path.parents:
        raise HTTPException(404, "Документ не найден")
    return path


@router.get("/offers-template.xlsx")
def get_offers_template(user: User = Depends(require_user)):
    if not member_anywhere(store, user):
        raise HTTPException(403, "Недостаточно прав")
    return Response(
        content=offers_template(),
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": "attachment; filename=offers-template.xlsx"},
    )


@router.get("/projects/{pid}/requests")
def get_requests(pid: str, user: User = Depends(require_user)):
    project = _member_project(user, pid)
    flags = access_flags(store, user, project)
    return {"ok": True, "data": {"requests": list_requests(store, project.id), "access": flags, "vat_rate": settings.vat_rate}}


@router.post("/projects/{pid}/requests")
def post_request(
    pid: str,
    body: RequestIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    project = _member_project(user, pid)
    _need(access_flags(store, user, project), "can_request")
    data = _idem(user, idempotency_key, body.model_dump_json(), lambda: create_request(store, project, user, body.title))
    return {"ok": True, "data": data}


@router.get("/projects/{pid}/picker")
def get_picker(pid: str, q: str = "", user: User = Depends(require_user)):
    project = _member_project(user, pid)
    return {"ok": True, "data": material_picker(store, project, q)}


@router.post("/projects/{pid}/quick")
def post_quick(
    pid: str,
    body: QuickIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    project = _member_project(user, pid)
    _need(access_flags(store, user, project), "can_request")
    data = _idem(user, idempotency_key, body.model_dump_json(), lambda: quick_request(store, project, user, body.title, body.unit, body.qty))
    return {"ok": True, "data": data}


@router.get("/inbox")
def get_inbox(user: User = Depends(require_user)):
    try:
        data = supplier_inbox(store, user)
    except PermissionError as exc:
        raise HTTPException(403, "Недостаточно прав") from exc
    return {"ok": True, "data": data}


@router.post("/requests/{rid}/repeat")
def post_repeat(
    rid: str,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req, project = _request(user, rid)
    _need(access_flags(store, user, project), "can_request")
    data = _idem(user, idempotency_key, f"repeat:{rid}", lambda: repeat_request(store, req, user))
    return {"ok": True, "data": data}


@router.get("/requests/{rid}/sheet")
def get_sheet(rid: str, user: User = Depends(require_user)):
    req, project = _request(user, rid)
    data = sheet_for(store, req)
    data["access"] = access_flags(store, user, project)
    data["vat_rate"] = settings.vat_rate
    return {"ok": True, "data": data}


@router.get("/requests/{rid}/savings")
def get_savings(rid: str, user: User = Depends(require_user)):
    req, _project = _request(user, rid)
    return {"ok": True, "data": savings_for_request(store, req)}


@router.get("/projects/{pid}/savings")
def get_project_savings(pid: str, user: User = Depends(require_user)):
    project = _member_project(user, pid)
    return {"ok": True, "data": project_savings(store, project.id)}


@router.get("/company-savings")
def get_company_savings(user: User = Depends(require_user)):
    return {"ok": True, "data": company_savings(store, user)}


@router.get("/requests/{rid}/export.xlsx")
def export_sheet(rid: str, user: User = Depends(require_user)):
    req, _project = _request(user, rid)
    data = sheet_for(store, req)
    content = comparison_workbook(data, req.title, savings_for_request(store, req))
    filename = f"comparison-{req.number}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/requests/{rid}/import-lines")
async def import_lines(
    rid: str,
    file: UploadFile = File(...),
    preview: bool = Query(default=False),
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req, project = _request(user, rid)
    _need(access_flags(store, user, project), "can_request")
    raw = await _bytes(file, MAX_XLSX)
    digest = hashlib.sha256(raw).hexdigest()

    def run():
        parsed = parse_statement(raw)
        if preview:
            return preview_lines(parsed["rows"], parsed["contact_ignored"])
        return apply_lines(store, req, parsed["rows"], parsed["contact_ignored"])

    return {"ok": True, "data": _idem(user, idempotency_key, f"lines:{int(preview)}:{digest}", run)}


@router.post("/requests/{rid}/import-offers")
async def import_offers(
    rid: str,
    file: UploadFile = File(...),
    supplier_name: str = Form(default=""),
    preview: bool = Query(default=False),
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req, project = _request(user, rid)
    _need(access_flags(store, user, project), "can_offer")
    raw = await _bytes(file, MAX_XLSX)
    digest = hashlib.sha256(raw).hexdigest()

    def run():
        parsed = parse_offers(raw)
        if preview:
            return preview_offers(parsed["rows"], parsed["contact_ignored"])
        return apply_offers(store, req, parsed["rows"], parsed["contact_ignored"], supplier_name)

    fingerprint = f"offers:{int(preview)}:{digest}:{supplier_name.strip()}"
    return {"ok": True, "data": _idem(user, idempotency_key, fingerprint, run)}


@router.post("/requests/{rid}/select-best")
def post_select_best(
    rid: str,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req, project = _request(user, rid)
    _need(access_flags(store, user, project), "can_decide")

    def run():
        select_best(store, req)
        data = sheet_for(store, req)
        data["access"] = access_flags(store, user, project)
        return data

    return {"ok": True, "data": _idem(user, idempotency_key, f"select-best:{rid}", run)}


@router.post("/requests/{rid}/documents")
async def post_document(
    rid: str,
    file: UploadFile = File(...),
    supplier_name: str = Form(...),
    doc_number: str = Form(default=""),
    doc_date: str = Form(default=""),
    amount_kzt: str = Form(default=""),
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req, project = _request(user, rid)
    _need(access_flags(store, user, project), "can_invoice")
    raw = await _bytes(file, MAX_DOC)
    mime, ext = _sniff_doc(raw)
    digest = hashlib.sha256(raw).hexdigest()
    amount = None
    if amount_kzt.strip():
        try:
            amount = float(amount_kzt.replace(" ", "").replace(",", "."))
        except ValueError as exc:
            raise HTTPException(400, "Сумма счёта должна быть числом") from exc
    stored_name = f"{uuid4().hex}{ext}"
    path = _doc_path(project.id, stored_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    meta = {
        "supplier_name": supplier_name,
        "doc_number": doc_number,
        "doc_date": doc_date,
        "amount_kzt": amount,
        "stored_name": stored_name,
        "mime": mime,
        "size": len(raw),
        "sha256": digest,
    }
    fingerprint = f"doc:{digest}:{supplier_name}:{doc_number}:{doc_date}:{amount}"
    data = _idem(user, idempotency_key, fingerprint, lambda: add_document(store, req, user, meta))
    return {"ok": True, "data": data}


@router.get("/documents/{did}/file")
def read_document(did: str, user: User = Depends(require_user)):
    doc, _req, project = _doc(user, did)
    path = _doc_path(project.id, doc.stored_name)
    if not path.is_file():
        raise HTTPException(404, "Документ не найден")
    return FileResponse(path, media_type=doc.mime, filename=f"invoice-{doc.id}{path.suffix}")


@router.patch("/documents/{did}")
def update_document(did: str, body: DocPatch, user: User = Depends(require_user)):
    doc, _req, project = _doc(user, did)
    _need(access_flags(store, user, project), "can_invoice")
    return {"ok": True, "data": _run(lambda: patch_document(store, doc, body.is_actual))}


@router.patch("/lines/{lid}")
def update_line(lid: str, body: LinePatch, user: User = Depends(require_user)):
    line, _req, project = _line(user, lid)
    _need(access_flags(store, user, project), "can_request")
    payload = body.model_dump(exclude_unset=True)
    return {"ok": True, "data": _run(lambda: patch_line(store, line, payload))}


@router.post("/lines/{lid}/offers")
def post_offer(
    lid: str,
    body: OfferIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    line, _req, project, as_supplier = _line_for_offer(user, lid)
    payload = body.model_dump()
    if as_supplier:
        payload["supplier_name"] = (user.company or user.full_name).strip()
    else:
        _need(access_flags(store, user, project), "can_offer")
    data = _idem(user, idempotency_key, body.model_dump_json(), lambda: add_offer(store, line, payload))
    return {"ok": True, "data": data}


@router.patch("/offers/{oid}")
def update_offer(oid: str, body: OfferPatch, user: User = Depends(require_user)):
    offer, _line, _req, project = _offer(user, oid)
    _need(access_flags(store, user, project), "can_offer")
    payload = body.model_dump(exclude_unset=True)
    return {"ok": True, "data": _run(lambda: patch_offer(store, offer, payload))}


@router.delete("/offers/{oid}")
def remove_offer(oid: str, user: User = Depends(require_user)):
    offer, _line, _req, project = _offer(user, oid)
    _need(access_flags(store, user, project), "can_offer")
    return {"ok": True, "data": _run(lambda: delete_offer(store, offer))}


@router.post("/lines/{lid}/select")
def post_select(
    lid: str,
    body: SelectIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    line, _req, project = _line(user, lid)
    _need(access_flags(store, user, project), "can_decide")
    data = _idem(
        user,
        idempotency_key,
        body.model_dump_json(),
        lambda: select_offer(store, line, body.offer_id),
    )
    return {"ok": True, "data": data}
