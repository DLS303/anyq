"""Object budget: plan, automatic procurement fact, and manual expenses."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from app.budget_models import CATEGORIES, BudgetCategory
from app.deps import require_user
from app.idempotency import IdempotencyConflict, run_idempotent
from app.media import strip_image
from app.schemas import User
from app.store import store
from app.store_budget import (
    BudgetConflict,
    add_expense,
    delete_expense,
    object_budget_view,
    photo_path,
    set_plan,
)
from app.store_procurement import access_flags

router = APIRouter(prefix="/v1/site", tags=["budget"])

MAX_PHOTO = 10 * 1024 * 1024


class BudgetPlanIn(BaseModel):
    total_kzt: int = Field(ge=0, le=10**12)
    materials_kzt: int | None = Field(default=None, ge=0, le=10**12)
    works_kzt: int | None = Field(default=None, ge=0, le=10**12)
    equipment_kzt: int | None = Field(default=None, ge=0, le=10**12)
    other_kzt: int | None = Field(default=None, ge=0, le=10**12)

    @model_validator(mode="after")
    def categories_fit(self):
        parts = [value for value in (self.materials_kzt, self.works_kzt, self.equipment_kzt, self.other_kzt) if value is not None]
        if parts and sum(parts) > self.total_kzt:
            raise ValueError("Сумма категорий больше общего бюджета")
        return self


class ExpenseIn(BaseModel):
    amount_kzt: int = Field(gt=0, le=10**12)
    category: BudgetCategory
    note: str = Field(default="", max_length=500)


def _project(pid: str):
    project = store.get_project(pid)
    if not project:
        raise HTTPException(404, "Проект не найден")
    return project


def _member(user: User, pid: str):
    project = _project(pid)
    if not store.can_access_project(user, project):
        raise HTTPException(403, "Недостаточно прав")
    return project


def _editor(user: User, project) -> None:
    if not access_flags(store, user, project).get("can_request"):
        raise HTTPException(403, "Недостаточно прав")


def _run(fn):
    try:
        return fn()
    except BudgetConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот запрос уже отправлен с другими данными") from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc) or "Не найдено") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _idem(user: User, key: str | None, fingerprint: str, fn):
    try:
        return run_idempotent(user.id, key, fingerprint, fn)
    except BudgetConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот запрос уже отправлен с другими данными") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _amount(raw) -> int:
    text = str(raw or "").strip().replace(" ", "")
    if not text:
        raise HTTPException(422, "Укажите сумму")
    if "," in text or "." in text:
        raise HTTPException(422, "Сумма должна быть целым числом тенге")
    try:
        value = int(text)
    except ValueError as exc:
        raise HTTPException(422, "Сумма должна быть целым числом тенге") from exc
    if value <= 0:
        raise HTTPException(422, "Сумма должна быть больше нуля")
    if value > 10**12:
        raise HTTPException(422, "Сумма слишком большая")
    return value


def _category(raw) -> str:
    text = str(raw or "").strip()
    if text not in CATEGORIES:
        raise HTTPException(422, "Неизвестная категория")
    return text


async def _photo(form) -> dict | None:
    upload = form.get("photo")
    if upload is None or isinstance(upload, str) or not getattr(upload, "filename", ""):
        return None
    data = await upload.read()
    if not data:
        return None
    if len(data) > MAX_PHOTO:
        raise HTTPException(422, "Файл больше 10 МБ")
    try:
        clean, mime, suffix = strip_image(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"data": clean, "mime": mime, "suffix": suffix, "sha256": hashlib.sha256(clean).hexdigest()}


@router.get("/projects/{pid}/object-budget")
def get_object_budget(pid: str, user: User = Depends(require_user)):
    project = _member(user, pid)
    return {"ok": True, "data": object_budget_view(store, project, user)}


@router.put("/projects/{pid}/object-budget")
def put_object_budget(
    pid: str,
    body: BudgetPlanIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    project = _member(user, pid)
    _editor(user, project)
    data = _idem(user, idempotency_key, body.model_dump_json(), lambda: set_plan(store, project, user, body.model_dump()))
    return {"ok": True, "data": data}


@router.post("/projects/{pid}/expenses")
async def post_expense(
    pid: str,
    request: Request,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    project = _member(user, pid)
    _editor(user, project)
    content = request.headers.get("content-type", "")
    photo = None
    if "multipart/form-data" in content:
        form = await request.form()
        payload = {
            "amount_kzt": _amount(form.get("amount_kzt")),
            "category": _category(form.get("category")),
            "note": str(form.get("note") or ""),
        }
        if len(payload["note"]) > 500:
            raise HTTPException(422, "Заметка длиннее 500 символов")
        photo = await _photo(form)
    else:
        try:
            body = ExpenseIn.model_validate(await request.json())
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, "Проверьте сумму, категорию и заметку") from exc
        payload = body.model_dump()
    fingerprint = f"{payload['amount_kzt']}|{payload['category']}|{payload['note']}|{photo['sha256'] if photo else ''}"
    data = _idem(
        user,
        idempotency_key,
        fingerprint,
        lambda: add_expense(store, project, user, payload, photo),
    )
    return {"ok": True, "data": data}


@router.delete("/projects/{pid}/expenses/{eid}")
def remove_expense(pid: str, eid: str, user: User = Depends(require_user)):
    project = _member(user, pid)
    _editor(user, project)
    item = store.object_expenses.get(eid)
    if not item or item.project_id != project.id:
        raise HTTPException(404, "Расход не найден")
    return {"ok": True, "data": _run(lambda: delete_expense(store, item))}


@router.get("/projects/{pid}/expenses/{eid}/photo")
def get_expense_photo(pid: str, eid: str, user: User = Depends(require_user)):
    project = _member(user, pid)
    item = store.object_expenses.get(eid)
    if not item or item.project_id != project.id or not item.photo_name:
        raise HTTPException(404, "Чек не найден")
    try:
        path = photo_path(project.id, item.photo_name)
    except LookupError as exc:
        raise HTTPException(404, "Чек не найден") from exc
    if not path.is_file():
        raise HTTPException(404, "Чек не найден")
    return FileResponse(path, media_type=item.photo_mime or "image/jpeg")
