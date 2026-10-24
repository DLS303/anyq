"""Completed-work act routes.

Ids come from the path. A query-string project id does not select another company.
The feature gate is 404 when the flag is off.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.deps import require_user
from app.idempotency import IdempotencyConflict, run_idempotent
from app.ks_acts import (
    Access,
    KsError,
    access_act,
    access_project,
    cancel_act,
    create_draft,
    export_ks2,
    export_ks3,
    ks3_report,
    list_acts,
    reject_act,
    reopen_act,
    sign_act,
    submit_act,
    update_lines,
)
from app.ks_files import MAX_PDF, PdfRejected
from app.schemas import User
from app.store import store

router = APIRouter(prefix="/v1/site", tags=["ks-acts"])


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=36, max_length=36)
    act_date: str = Field(min_length=10, max_length=10)
    period_from: str = Field(min_length=10, max_length=10)
    period_to: str = Field(min_length=10, max_length=10)
    contract_ref: str | None = Field(default=None, max_length=120)


class LineIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=36, max_length=36)
    qty_period: Decimal = Field(ge=0, le=Decimal(1000000000))


class LinesIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    row_version: int = Field(ge=1, le=1_000_000)
    lines: list[LineIn] = Field(max_length=500)


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    row_version: int = Field(ge=1, le=1_000_000)


class RejectIn(VersionIn):
    reason_code: str = Field(min_length=1, max_length=40)


def _guard(act_id: str | None, pid: str | None, user: User) -> Access:
    if act_id:
        return access_act(act_id, user)
    if pid:
        return access_project(pid, user)
    raise HTTPException(status_code=404, detail="Не найдено")


def require_ks(request: Request, user: User = Depends(require_user)) -> Access:
    path = request.path_params
    return _guard(path.get("act_id"), path.get("pid"), user)


def _run(access: Access, key: str | None, fingerprint: str, create, *, scope: str):
    try:
        data = run_idempotent(
            access.user.id,
            key,
            fingerprint,
            create,
            company_id=access.company_id,
            scope=scope,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "idempotency"}) from exc
    except KsError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from exc
    return {"ok": True, "data": data}


def _file(payload: tuple[bytes, str, str]) -> Response:
    body, media, name = payload
    return Response(
        content=body,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


async def _read_pdf(request: Request) -> tuple[bytes, int]:
    form = await request.form()
    upload = form.get("file")
    version_raw = form.get("row_version")
    if upload is None or isinstance(upload, str):
        raise HTTPException(status_code=422, detail={"code": "file_required"})
    chunks: list[bytes] = []
    total = 0
    while True:
        block = await upload.read(1024 * 1024)
        if not block:
            break
        total += len(block)
        if total > MAX_PDF:
            raise HTTPException(status_code=413, detail={"code": "too_large"})
        chunks.append(block)
    try:
        version = int(str(version_raw or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_version"}) from exc
    if version < 1:
        raise HTTPException(status_code=422, detail={"code": "invalid_version"})
    return b"".join(chunks), version


@router.get("/projects/{pid}/ks-acts")
def get_acts(access: Access = Depends(require_ks)):
    return {"ok": True, "data": list_acts(access.project.id)}


@router.post("/projects/{pid}/ks-acts")
def post_act(
    body: DraftIn,
    access: Access = Depends(require_ks),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(access, idempotency_key, body.model_dump_json(), lambda: create_draft(access, body.model_dump()), scope="ks_act.create")


@router.get("/projects/{pid}/ks3")
def get_ks3(period_from: str, period_to: str, access: Access = Depends(require_ks)):
    try:
        data = ks3_report(access, period_from, period_to)
    except KsError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from exc
    return {"ok": True, "data": data}


@router.get("/projects/{pid}/ks3.pdf")
def get_ks3_pdf(period_from: str, period_to: str, access: Access = Depends(require_ks)):
    try:
        return _file(export_ks3(access, period_from, period_to, "pdf"))
    except KsError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from exc


@router.get("/projects/{pid}/ks3.xlsx")
def get_ks3_xlsx(period_from: str, period_to: str, access: Access = Depends(require_ks)):
    try:
        return _file(export_ks3(access, period_from, period_to, "xlsx"))
    except KsError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from exc


@router.get("/ks-acts/{act_id}")
def get_act(access: Access = Depends(require_ks)):
    return {"ok": True, "data": access.act}


@router.put("/ks-acts/{act_id}/lines")
def put_lines(
    body: LinesIn,
    access: Access = Depends(require_ks),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(
        access,
        idempotency_key,
        body.model_dump_json(),
        lambda: update_lines(access, body.model_dump(mode="json")),
        scope="ks_act.lines",
    )


@router.post("/ks-acts/{act_id}/submit")
def post_submit(
    body: VersionIn,
    access: Access = Depends(require_ks),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(access, idempotency_key, body.model_dump_json(), lambda: submit_act(access, body.row_version), scope="ks_act.submit")


@router.post("/ks-acts/{act_id}/reject")
def post_reject(
    body: RejectIn,
    access: Access = Depends(require_ks),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(
        access,
        idempotency_key,
        body.model_dump_json(),
        lambda: reject_act(access, body.row_version, body.reason_code),
        scope="ks_act.reject",
    )


@router.post("/ks-acts/{act_id}/cancel")
def post_cancel(
    body: VersionIn,
    access: Access = Depends(require_ks),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(access, idempotency_key, body.model_dump_json(), lambda: cancel_act(access, body.row_version), scope="ks_act.cancel")


@router.post("/ks-acts/{act_id}/draft")
def post_draft(
    body: VersionIn,
    access: Access = Depends(require_ks),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(access, idempotency_key, body.model_dump_json(), lambda: reopen_act(access, body.row_version), scope="ks_act.draft")


@router.post("/ks-acts/{act_id}/sign")
async def post_sign(
    request: Request,
    access: Access = Depends(require_ks),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    from hashlib import sha256

    raw, version = await _read_pdf(request)
    digest = sha256(raw).hexdigest()

    def create():
        try:
            return sign_act(access, version, raw)
        except PdfRejected as exc:
            raise KsError(415, exc.code) from exc

    return _run(access, idempotency_key, f"{version}:{digest}", create, scope="ks_act.sign")


@router.get("/ks-acts/{act_id}/ks2.pdf")
def get_ks2_pdf(access: Access = Depends(require_ks)):
    return _file(export_ks2(access, "pdf"))


@router.get("/ks-acts/{act_id}/ks2.xlsx")
def get_ks2_xlsx(access: Access = Depends(require_ks)):
    return _file(export_ks2(access, "xlsx"))


@router.get("/ks-acts/{act_id}/file")
def get_signed_file(access: Access = Depends(require_ks)):
    act = access.act or {}
    file_id = act.get("signed_file_id")
    item = store.get_upload(file_id) if file_id else None
    if item is None or item.project_id != access.project.id:
        raise HTTPException(status_code=404, detail="Не найдено")
    from app.paths import resolve_stored_file

    try:
        path = resolve_stored_file(item.kind, item.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Не найдено") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Не найдено")
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="signed.pdf"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
