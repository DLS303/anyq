"""Object budget collections. Callers pass the store."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from app.budget_calc import (
    combine_savings,
    forecast_overrun,
    manual_actual,
    merge_fact,
    plan_vs_chosen,
    planned_window,
    procurement_actual,
    signal_for,
)
from app.budget_models import CATEGORIES, ObjectBudget, ObjectExpense
from app.config import settings
from app.paths import uploads_dir
from app.procurement_calc import clean_note, compute_savings, pos_key
from app.store_procurement import access_flags


class BudgetConflict(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def today_date() -> date:
    return date.today()


def load_budget(store, raw: dict) -> None:
    store.object_budgets = {}
    for item in raw.get("object_budgets", []):
        row = ObjectBudget.model_validate(item)
        store.object_budgets[row.project_id] = row
    store.object_expenses = {item["id"]: ObjectExpense.model_validate(item) for item in raw.get("object_expenses", [])}


def dump_budget(store) -> dict:
    return {
        "object_budgets": [item.model_dump() for item in store.object_budgets.values()],
        "object_expenses": [item.model_dump() for item in store.object_expenses.values()],
    }


def _company_key(name: str) -> str:
    return " ".join((name or "").casefold().split())


def photo_path(project_id: str, name: str) -> Path:
    if not project_id or any(part in project_id for part in ("/", "\\", "..")):
        raise LookupError("Чек не найден")
    if not name or any(part in name for part in ("/", "\\", "..")):
        raise LookupError("Чек не найден")
    root = (uploads_dir() / project_id / "expenses").resolve()
    path = (root / name).resolve()
    if path.parent != root:
        raise LookupError("Чек не найден")
    return path


def _request_lines(store, project_id: str):
    request_ids = {item.id for item in store.proc_requests.values() if item.project_id == project_id}
    lines = [item for item in store.proc_lines.values() if item.request_id in request_ids]
    line_ids = {item.id for item in lines}
    offers = [item for item in store.proc_offers.values() if item.line_id in line_ids]
    docs = [item for item in store.proc_docs.values() if item.request_id in request_ids]
    return lines, offers, docs


def savings_for_request(store, request) -> dict:
    lines = [item for item in store.proc_lines.values() if item.request_id == request.id]
    lines.sort(key=lambda line: (pos_key(line.pos_no), line.id))
    ids = {line.id for line in lines}
    offers = [item for item in store.proc_offers.values() if item.line_id in ids]
    docs = [item for item in store.proc_docs.values() if item.request_id == request.id]
    return compute_savings(lines, offers, settings.vat_rate, settings.overprice_threshold, docs)


def project_savings(store, project_id: str) -> dict:
    requests = [item for item in store.proc_requests.values() if item.project_id == project_id]
    requests.sort(key=lambda item: item.number)
    return combine_savings([savings_for_request(store, item) for item in requests])


def company_projects(store, user) -> list:
    key = _company_key(user.company)
    chosen = []
    for project in store.projects.values():
        if not store.can_access_project(user, project):
            continue
        if not key:
            chosen.append(project)
            continue
        owner = store.get_user(project.owner_id) if project.owner_id else None
        owner_key = _company_key(owner.company) if owner else ""
        directory_keys = {
            _company_key(row.company) for row in store.directory.values() if row.project_id == project.id and row.company
        }
        if owner_key == key or key in directory_keys or project.owner_id == user.id:
            chosen.append(project)
    chosen.sort(key=lambda item: (item.title, item.id))
    return chosen


def company_savings(store, user) -> dict:
    projects = company_projects(store, user)
    objects = []
    parts = []
    for project in projects:
        summary = project_savings(store, project.id)
        parts.append(summary)
        objects.append(
            {
                "project_id": project.id,
                "title": project.title,
                "savings_kzt": summary["savings_kzt"],
                "base_kzt": summary["base_kzt"],
                "savings_pct": summary["savings_pct"],
            }
        )
    combined = combine_savings(parts)
    combined["company"] = user.company
    combined["objects"] = objects
    return combined


def _public_expense(item: ObjectExpense) -> dict:
    return {
        "id": item.id,
        "amount_kzt": item.amount_kzt,
        "category": item.category,
        "note": item.note,
        "has_photo": bool(item.photo_name),
        "created_at": item.created_at,
    }


def _savings_brief(summary: dict) -> dict:
    return {
        "savings_kzt": summary["savings_kzt"],
        "base_kzt": summary["base_kzt"],
        "savings_pct": summary["savings_pct"],
        "requests": summary["requests"],
    }


def object_budget_view(store, project, user) -> dict:
    plan = store.object_budgets.get(project.id)
    expenses = [item for item in store.object_expenses.values() if item.project_id == project.id]
    expenses.sort(key=lambda item: (item.created_at, item.id), reverse=True)
    lines, offers, docs = _request_lines(store, project.id)
    procured = procurement_actual(lines, offers, docs, settings.vat_rate)
    manual = manual_actual(expenses)
    fact_by = merge_fact(procured, manual)
    fact = sum(fact_by.values())
    planned = plan.total_kzt if plan else 0
    if plan is None:
        tone, pct = ("red", None) if fact > 0 else ("green", None)
        remaining = None
    else:
        tone, pct = signal_for(fact, planned)
        remaining = planned - fact
    tasks = [task for task in store.schedule.values() if task.project_id == project.id]
    window = planned_window(project.start, project.finish, [(task.start, task.finish) for task in tasks])
    start, finish = window if window else (None, None)
    forecast = forecast_overrun(planned if plan else 0, fact, start, finish, today_date())
    savings = project_savings(store, project.id)
    company = company_savings(store, user)
    compared = plan_vs_chosen(lines, offers, settings.vat_rate)
    if not compared["lines"] and plan is not None and plan.materials_kzt is not None:
        chosen = int(procured.get("materials") or 0)
        compared = {
            "lines": [],
            "plan_kzt": int(plan.materials_kzt),
            "chosen_kzt": chosen,
            "total_saved_kzt": int(plan.materials_kzt) - chosen,
        }
    return {
        "plan": {
            "set": plan is not None,
            "total_kzt": planned,
            "materials_kzt": plan.materials_kzt if plan else None,
            "works_kzt": plan.works_kzt if plan else None,
            "equipment_kzt": plan.equipment_kzt if plan else None,
            "other_kzt": plan.other_kzt if plan else None,
        },
        "fact_kzt": fact,
        "fact_by_category": fact_by,
        "procurement_kzt": sum(procured.values()),
        "manual_kzt": sum(manual.values()),
        "remaining_kzt": remaining,
        "used_pct": pct,
        "signal": tone,
        "elapsed_share": forecast["elapsed_share"],
        "elapsed_days": forecast["elapsed_days"],
        "span_days": forecast["span_days"],
        "schedule_start": forecast["schedule_start"],
        "schedule_finish": forecast["schedule_finish"],
        "forecast_kzt": forecast["forecast_kzt"],
        "forecast_raw_kzt": forecast["forecast_raw_kzt"],
        "forecast_bound_kzt": forecast["forecast_bound_kzt"],
        "forecast_reason": forecast["forecast_reason"],
        "overrun_kzt": forecast["overrun_kzt"],
        "overrun_kind": forecast["overrun_kind"],
        "plan_vs_chosen": compared,
        "savings": _savings_brief(savings),
        "company": {"name": company["company"], **_savings_brief(company)},
        "expenses": [_public_expense(item) for item in expenses],
        "can_edit": bool(access_flags(store, user, project).get("can_request")),
    }


def set_plan(store, project, user, payload: dict) -> dict:
    categories = {key: payload.get(f"{key}_kzt") for key in CATEGORIES}
    plan = ObjectBudget(
        project_id=project.id,
        total_kzt=int(payload["total_kzt"]),
        materials_kzt=categories["materials"],
        works_kzt=categories["works"],
        equipment_kzt=categories["equipment"],
        other_kzt=categories["other"],
        updated_at=_now(),
        updated_by=user.id,
    )
    with store._lock:
        store.object_budgets[project.id] = plan
        store._save_unlocked()
    return object_budget_view(store, project, user)


def add_expense(store, project, user, payload: dict, photo: dict | None = None) -> dict:
    amount = int(payload["amount_kzt"])
    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    category = payload["category"]
    if category not in CATEGORIES:
        raise ValueError("Неизвестная категория")
    note = clean_note(payload.get("note") or "")
    with store._lock:
        if photo:
            digest = photo["sha256"]
            clash = any(
                item.project_id == project.id and item.photo_sha256 == digest for item in store.object_expenses.values()
            )
            if clash:
                raise BudgetConflict("Этот чек уже внесён")
            folder = uploads_dir() / project.id / "expenses"
            folder.mkdir(parents=True, exist_ok=True)
            stored = f"{uuid4().hex}{photo['suffix']}"
            target = photo_path(project.id, stored)
            target.write_bytes(photo["data"])
        else:
            stored = ""
            digest = ""
        item = ObjectExpense(
            id=uuid4().hex,
            project_id=project.id,
            amount_kzt=amount,
            category=category,
            note=note,
            photo_name=stored,
            photo_mime=photo["mime"] if photo else "",
            photo_sha256=digest if photo else "",
            created_at=_now(),
            created_by=user.id,
        )
        store.object_expenses[item.id] = item
        store._save_unlocked()
        return object_budget_view(store, project, user)


def delete_expense(store, expense: ObjectExpense) -> dict:
    with store._lock:
        store.object_expenses.pop(expense.id, None)
        store._save_unlocked()
    if expense.photo_name:
        try:
            path = photo_path(expense.project_id, expense.photo_name)
        except LookupError:
            path = None
        if path is not None and path.is_file():
            path.unlink()
    return {"id": expense.id}
