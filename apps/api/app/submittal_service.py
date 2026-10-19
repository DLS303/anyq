"""Material approvals stored in their own tables.

Writes use compare-and-swap on row_version. Numbers are unique per project.
A file id is unique on one approval. Approver links are revoked on withdraw,
a final decision, and delete.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app import audit
from app.company_features import feature_open_for_company, project_company_id
from app.media import strip_image, strip_pdf_author
from app.paths import discard_temp, publish_exclusive, resolve_stored_file, write_exclusive_temp
from app.procurement_calc import clean_note, strip_contacts
from app.rfi_service import PUSH_BODY, add_business_days, push_payload
from app.rfi_tables import access_tokens
from app.shares import hashes_match, new_share_token, parse_expiry, token_hash
from app.store import store
from app.submittal_tables import (
    material_approval_analogs,
    material_approval_files,
    material_approval_specs,
    material_approval_steps,
    material_approval_suppliers,
    material_approvals,
)

PURPOSE = "submittal_decision"
LINK_MIN_DAYS = 14
LINK_MAX_DAYS = 30
FILE_KINDS = {"cert", "passport", "declaration", "photo", "quote", "invoice"}
PRICE_KINDS = {"quote", "invoice"}
DECISIONS = {"approved", "approved_with_note", "rejected"}
APPROVED = {"approved", "approved_with_note"}
NOTE_REQUIRED = {"rejected", "approved_with_note"}
TERMINAL = APPROVED | {"rejected", "withdrawn"}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DUPLICATE_WARNING = "этот файл уже загружен к счёту {label}"


class StatusConflict(Exception):
    """Procurement tried to send a line that is not approved yet."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _today() -> date:
    return datetime.now(UTC).date()


def _storage_key() -> str:
    return uuid4().hex


def _uuid(value: str) -> str:
    if not value or not _UUID.match(value):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    return value.lower()


def _text(value: str, limit: int, *, required: bool = False) -> str:
    cleaned, _removed = strip_contacts(str(value or ""))
    cleaned = " ".join(cleaned.split())[:limit]
    if required and not cleaned:
        raise HTTPException(status_code=400, detail="Укажите поле")
    return cleaned


def _conflict() -> None:
    raise HTTPException(status_code=409, detail="Изменено другим")


def _member(project, user_id: str) -> bool:
    if project is not None and project.owner_id == user_id:
        return True
    return any(
        row.project_id == getattr(project, "id", "") and row.user_id == user_id for row in store.directory.values()
    )


def _audit(session, action, entity_id, project_id, changes, *, company_id, actor_user_id, actor_kind="user") -> None:
    audit.write(
        action,
        "material_approval",
        entity_id,
        project_id,
        changes,
        session=session,
        company_id=company_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
    )


def _load(session, approval_id: str):
    return session.execute(
        select(material_approvals).where(material_approvals.c.id == approval_id)
    ).mappings().first()


def _children(session, table, approval_id: str):
    return session.execute(
        select(table).where(table.c.approval_id == approval_id, table.c.deleted_at.is_(None)).order_by(table.c.created_at)
    ).mappings().all()


def _steps(session, approval_id: str):
    return session.execute(
        select(material_approval_steps)
        .where(
            material_approval_steps.c.approval_id == approval_id,
            material_approval_steps.c.deleted_at.is_(None),
        )
        .order_by(material_approval_steps.c.step_order)
    ).mappings().all()


def project_id_of(approval_id: str) -> str:
    try:
        with store._sql.factory() as session:
            found = session.scalar(
                select(material_approvals.c.project_id).where(
                    material_approvals.c.id == approval_id,
                    material_approvals.c.deleted_at.is_(None),
                )
            )
    except (OperationalError, ProgrammingError):
        return ""
    return str(found or "")


def _cas(session, approval_id: str, version: int, values: dict, *, updated_by: str) -> None:
    result = session.execute(
        update(material_approvals)
        .where(
            material_approvals.c.id == approval_id,
            material_approvals.c.row_version == version,
            material_approvals.c.deleted_at.is_(None),
        )
        .values(**values, updated_by=updated_by or "", row_version=version + 1, updated_at=_now())
    )
    if result.rowcount != 1:
        session.rollback()
        _conflict()


def _revoke_links(session, entity_id: str, stamp: str, actor: str) -> None:
    session.execute(
        update(access_tokens)
        .where(
            access_tokens.c.entity_id == entity_id,
            access_tokens.c.purpose == PURPOSE,
            access_tokens.c.deleted_at.is_(None),
        )
        .values(
            deleted_at=stamp,
            updated_at=stamp,
            updated_by=actor or "",
            row_version=access_tokens.c.row_version + 1,
        )
    )


def _next_number(session, project_id: str) -> str:
    rows = session.scalars(
        select(material_approvals.c.number).where(material_approvals.c.project_id == project_id)
    ).all()
    highest = 0
    for raw in rows:
        match = re.search(r"(\d+)$", str(raw or ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"MAT-{highest + 1:03d}"


def _insert_numbered(session, values: dict) -> str:
    last = None
    for _ in range(8):
        number = _next_number(session, values["project_id"])
        try:
            with session.begin_nested():
                session.execute(material_approvals.insert().values(**values, number=number))
            return number
        except IntegrityError as exc:
            last = exc
    raise HTTPException(status_code=409, detail="Изменено другим") from last


def _overdue(status: str, need_by: str | None, today: date | None = None) -> bool:
    if status not in {"draft", "in_review"} or not need_by:
        return False
    try:
        return date.fromisoformat(need_by) < (today or _today())
    except ValueError:
        return False


def _remind(status: str, need_by: str | None, today: date | None = None) -> bool:
    if status not in {"draft", "in_review"} or not need_by:
        return False
    try:
        due = date.fromisoformat(need_by)
    except ValueError:
        return False
    return (today or _today()) + timedelta(days=1) == due


def _budget_warning(project_id: str, price, qty) -> bool:
    if price is None:
        return False
    plan = store.object_budgets.get(project_id)
    if plan is None:
        return False
    cap = plan.materials_kzt if plan.materials_kzt is not None else plan.total_kzt
    if cap is None:
        return False
    return float(price) * float(qty) > float(cap)


def _pack(session, row, viewer_id: str) -> dict:
    specs = _children(session, material_approval_specs, row.id)
    analogs = _children(session, material_approval_analogs, row.id)
    suppliers = _children(session, material_approval_suppliers, row.id)
    files = _children(session, material_approval_files, row.id)
    steps = _steps(session, row.id)
    pending = next((step for step in steps if not step.decision), None)
    versions = session.execute(
        select(
            material_approvals.c.id,
            material_approvals.c.version,
            material_approvals.c.status,
            material_approvals.c.parent_id,
        )
        .where(material_approvals.c.root_id == row.root_id, material_approvals.c.deleted_at.is_(None))
        .order_by(material_approvals.c.version)
    ).mappings().all()
    price = row.indicative_price if row.price_file_id else None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "root_id": row.root_id,
        "parent_id": row.parent_id,
        "number": row.number,
        "request_item_id": row.request_item_id,
        "name": row.name,
        "brand": row.brand,
        "manufacturer": row.manufacturer or "",
        "unit": row.unit,
        "qty": row.qty,
        "need_by": row.need_by,
        "status": row.status,
        "version": int(row.version),
        "indicative_price": price,
        "price_file_id": row.price_file_id if price is not None else None,
        "author_id": row.author_id,
        "comment": row.comment or "",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "row_version": int(row.row_version),
        "deleted_at": row.deleted_at,
        "overdue": _overdue(row.status, row.need_by),
        "remind": _remind(row.status, row.need_by),
        "budget_warning": _budget_warning(row.project_id, price, row.qty),
        "can_decide": bool(pending and viewer_id and pending.approver_user_id == viewer_id and row.status == "in_review"),
        "pending_approver_id": pending.approver_user_id if pending and row.status == "in_review" else None,
        "project_only": True,
        "specs": [{"id": item.id, "param": item.param, "value": item.value} for item in specs],
        "analogs": [
            {"id": item.id, "brand": item.brand, "manufacturer": item.manufacturer or ""} for item in analogs
        ],
        "suppliers": [{"id": item.id, "name": item.supplier_name} for item in suppliers],
        "files": [
            {"id": item.id, "file_id": item.file_id, "kind": item.kind, "size": item.size, "sha256": item.sha256}
            for item in files
        ],
        "steps": [
            {
                "id": item.id,
                "approver_user_id": item.approver_user_id,
                "order": int(item.step_order),
                "decision": item.decision,
                "comment": item.comment or "",
                "decided_at": item.decided_at,
            }
            for item in steps
        ],
        "versions": [
            {"id": item.id, "version": int(item.version), "status": item.status, "parent_id": item.parent_id}
            for item in versions
        ],
    }


def _saved(approval_id: str, viewer_id: str) -> dict:
    with store._sql.factory() as session:
        row = _load(session, approval_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        return _pack(session, row, viewer_id)


def _notify(data: dict) -> list[str]:
    ids = [data["author_id"]]
    if data.get("pending_approver_id") and data["pending_approver_id"] not in ids:
        ids.append(data["pending_approver_id"])
    return ids


def _with_push(data: dict) -> dict:
    data["push"] = push_payload(data["id"])
    data["notify"] = _notify(data)
    return data


def _due(value: str | None) -> str:
    if not value:
        return add_business_days(_today(), 5).isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректная дата") from exc


def _stamp_row(company_id: str, project_id: str, actor: str, stamp: str) -> dict:
    return {
        "company_id": company_id,
        "project_id": project_id,
        "created_by": actor,
        "updated_by": actor,
        "created_at": stamp,
        "updated_at": stamp,
        "row_version": 1,
        "deleted_at": None,
    }


def _insert_specs(session, approval_id: str, company_id: str, project_id: str, actor: str, stamp: str, specs: list) -> None:
    for index, item in enumerate(specs):
        param = _text(item.get("param") if isinstance(item, dict) else "", 200, required=True)
        value = _text(item.get("value") if isinstance(item, dict) else "", 500, required=True)
        session.execute(
            material_approval_specs.insert().values(
                id=str(uuid4()),
                approval_id=approval_id,
                param=param,
                value=value,
                position=index,
                **_stamp_row(company_id, project_id, actor, stamp),
            )
        )


def _insert_analogs(session, approval_id, company_id, project_id, actor, stamp, analogs: list) -> None:
    for item in analogs:
        if not isinstance(item, dict):
            continue
        brand = _text(item.get("brand"), 200)
        if not brand:
            continue
        session.execute(
            material_approval_analogs.insert().values(
                id=str(uuid4()),
                approval_id=approval_id,
                brand=brand,
                manufacturer=_text(item.get("manufacturer"), 200) or None,
                **_stamp_row(company_id, project_id, actor, stamp),
            )
        )


def _insert_suppliers(session, approval_id, company_id, project_id, actor, stamp, names: list) -> None:
    for raw in names:
        name = _text(raw if isinstance(raw, str) else (raw or {}).get("name", ""), 200)
        if not name:
            continue
        session.execute(
            material_approval_suppliers.insert().values(
                id=str(uuid4()),
                approval_id=approval_id,
                supplier_name=name,
                **_stamp_row(company_id, project_id, actor, stamp),
            )
        )


def _insert_steps(session, approval_id, company_id, project_id, actor, stamp, approvers: list[str]) -> None:
    seen = []
    for raw in approvers:
        approver = str(raw or "").strip()
        if approver and approver not in seen:
            seen.append(approver)
    for index, approver in enumerate(seen, start=1):
        session.execute(
            material_approval_steps.insert().values(
                id=str(uuid4()),
                approval_id=approval_id,
                approver_user_id=approver,
                step_order=index,
                decision=None,
                comment=None,
                decided_at=None,
                **_stamp_row(company_id, project_id, actor, stamp),
            )
        )


def create_approval(user, access: dict, body: dict) -> dict:
    project = store.get_project(access["project_id"])
    if project is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    company_id = project_company_id(project)
    if not company_id or company_id != access["company_id"]:
        raise HTTPException(status_code=404, detail="Не найдено")
    record_id = _uuid(str(body.get("id") or ""))
    name = _text(body.get("name"), 200, required=True)
    brand = _text(body.get("brand"), 200, required=True)
    sent_version = body.get("row_version")
    if sent_version not in (None, 0, 1):
        _conflict()
    approvers = [str(item) for item in (body.get("approver_ids") or []) if str(item).strip()]
    for approver in approvers:
        if not _member(project, approver):
            raise HTTPException(status_code=404, detail="Не найдено")
    specs = list(body.get("specs") or [])
    if not specs:
        specs = [{"param": "mark", "value": brand}]
    unit = _text(body.get("unit"), 40) or "шт"
    qty_raw = body.get("qty")
    qty = 1.0 if qty_raw in (None, "") else float(qty_raw)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Количество должно быть больше нуля")
    price = body.get("indicative_price")
    price_file = str(body.get("price_file_id") or "").strip() or None
    if price is not None and not price_file:
        price = None
    stamp = _now()
    values = {
        "id": record_id,
        "company_id": company_id,
        "project_id": project.id,
        "root_id": record_id,
        "parent_id": None,
        "request_item_id": _text(body.get("request_item_id"), 80) or None,
        "name": name,
        "brand": brand,
        "manufacturer": _text(body.get("manufacturer"), 200) or None,
        "unit": unit,
        "qty": qty,
        "need_by": _due(body.get("need_by")),
        "status": "draft",
        "version": 1,
        "indicative_price": None if price is None else float(price),
        "price_file_id": None,
        "author_id": user.id,
        "comment": None,
        "created_by": user.id,
        "updated_by": user.id,
        "created_at": stamp,
        "updated_at": stamp,
        "row_version": 1,
        "deleted_at": None,
    }
    session = store._sql.factory()
    try:
        _insert_numbered(session, values)
        _insert_specs(session, record_id, company_id, project.id, user.id, stamp, specs)
        _insert_analogs(session, record_id, company_id, project.id, user.id, stamp, list(body.get("analogs") or []))
        _insert_suppliers(session, record_id, company_id, project.id, user.id, stamp, list(body.get("suppliers") or []))
        _insert_steps(session, record_id, company_id, project.id, user.id, stamp, approvers)
        _audit(
            session,
            "submittal.create",
            record_id,
            project.id,
            {"status": "draft"},
            company_id=company_id,
            actor_user_id=user.id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    finally:
        session.close()
    return _with_push(_saved(record_id, user.id))


def list_for_user(user, project_id: str) -> dict:
    with store._sql.factory() as session:
        rows = session.execute(
            select(material_approvals)
            .where(material_approvals.c.project_id == project_id, material_approvals.c.deleted_at.is_(None))
            .order_by(material_approvals.c.created_at)
        ).mappings().all()
        items = [_pack(session, row, user.id) for row in rows]
    return {"items": items, "overdue": sum(1 for item in items if item["overdue"])}


def read_for_user(user, approval_id: str) -> dict:
    return _saved(approval_id, user.id)


def _require_ready(session, row) -> None:
    files = session.scalar(
        select(func.count())
        .select_from(material_approval_files)
        .where(
            material_approval_files.c.approval_id == row.id,
            material_approval_files.c.deleted_at.is_(None),
        )
    )
    steps = session.scalar(
        select(func.count())
        .select_from(material_approval_steps)
        .where(material_approval_steps.c.approval_id == row.id, material_approval_steps.c.deleted_at.is_(None))
    )
    if not files or not steps or not row.name or not row.brand:
        raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")


def set_status(
    user,
    approval_id: str,
    status: str,
    row_version: int,
    comment: str = "",
    *,
    token_id: str | None = None,
    token_version: int | None = None,
) -> dict:
    note = _text(comment, 2000)
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        previous = row.status
        actor = "" if user is None else user.id
        stamp = _now()
        values: dict = {}
        if status == "in_review":
            if previous != "draft":
                session.rollback()
                raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
            _require_ready(session, row)
            values["status"] = "in_review"
        elif status == "withdrawn":
            if previous not in {"draft", "in_review"} or (user is not None and row.author_id != user.id):
                session.rollback()
                raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
            values["status"] = "withdrawn"
            _revoke_links(session, approval_id, stamp, actor)
        elif status in DECISIONS:
            if previous != "in_review":
                session.rollback()
                raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
            steps = _steps(session, approval_id)
            pending = next((step for step in steps if not step.decision), None)
            if pending is None:
                session.rollback()
                raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
            if user is not None and pending.approver_user_id != user.id:
                session.rollback()
                raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
            if status in NOTE_REQUIRED and not note:
                session.rollback()
                raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
            spent = session.execute(
                update(material_approval_steps)
                .where(
                    material_approval_steps.c.id == pending.id,
                    material_approval_steps.c.row_version == int(pending.row_version),
                    material_approval_steps.c.decision.is_(None),
                )
                .values(
                    decision=status,
                    comment=note or None,
                    decided_at=stamp,
                    updated_by=actor,
                    updated_at=stamp,
                    row_version=int(pending.row_version) + 1,
                )
            )
            if spent.rowcount != 1:
                session.rollback()
                _conflict()
            later = [step for step in steps if int(step.step_order) > int(pending.step_order) and not step.decision]
            final = status if status == "rejected" or not later else "in_review"
            values["status"] = final
            if note:
                values["comment"] = note
            if token_id is not None:
                used = session.execute(
                    update(access_tokens)
                    .where(
                        access_tokens.c.id == token_id,
                        access_tokens.c.used_at.is_(None),
                        access_tokens.c.deleted_at.is_(None),
                        access_tokens.c.row_version == int(token_version or 0),
                    )
                    .values(
                        used_at=stamp,
                        updated_by="",
                        row_version=int(token_version or 0) + 1,
                        updated_at=stamp,
                    )
                )
                if used.rowcount != 1:
                    session.rollback()
                    raise HTTPException(status_code=410, detail="Срок ссылки истёк")
            if final in TERMINAL:
                _revoke_links(session, approval_id, stamp, actor)
        else:
            session.rollback()
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        _cas(session, approval_id, int(row_version), values, updated_by=actor)
        _audit(
            session,
            "submittal.status_change",
            approval_id,
            row.project_id,
            {"status": [previous, values["status"]]},
            company_id=row.company_id,
            actor_user_id=None if user is None else user.id,
            actor_kind="user" if user is not None else "token",
        )
        session.commit()
    finally:
        session.close()
    return _with_push(_saved(approval_id, "" if user is None else user.id))


def tombstone(user, approval_id: str, row_version: int) -> dict:
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        stamp = _now()
        _revoke_links(session, approval_id, stamp, user.id)
        _cas(session, approval_id, int(row_version), {"deleted_at": stamp, "status": row.status}, updated_by=user.id)
        _audit(
            session,
            "submittal.delete",
            approval_id,
            row.project_id,
            {"row_version": int(row_version) + 1},
            company_id=row.company_id,
            actor_user_id=user.id,
        )
        session.commit()
    finally:
        session.close()
    return {"id": approval_id, "deleted_at": stamp}


def new_version(user, approval_id: str, body: dict) -> dict:
    record_id = _uuid(str(body.get("id") or ""))
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        if row.status != "rejected":
            session.rollback()
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        if int(row.row_version) != int(body.get("row_version")):
            session.rollback()
            _conflict()
        stamp = _now()
        base = _stamp_row(row.company_id, row.project_id, user.id, stamp)
        values = {
            "id": record_id,
            "company_id": row.company_id,
            "project_id": row.project_id,
            "root_id": row.root_id,
            "parent_id": row.id,
            "request_item_id": row.request_item_id,
            "name": row.name,
            "brand": row.brand,
            "manufacturer": row.manufacturer,
            "unit": row.unit,
            "qty": row.qty,
            "need_by": row.need_by,
            "status": "draft",
            "version": int(row.version) + 1,
            "indicative_price": None,
            "price_file_id": None,
            "author_id": row.author_id,
            "comment": None,
            "created_by": user.id,
            "updated_by": user.id,
            "created_at": stamp,
            "updated_at": stamp,
            "row_version": 1,
            "deleted_at": None,
        }
        _insert_numbered(session, values)
        for item in _children(session, material_approval_specs, row.id):
            session.execute(
                material_approval_specs.insert().values(
                    id=str(uuid4()),
                    approval_id=record_id,
                    param=item.param,
                    value=item.value,
                    position=item.position,
                    **base,
                )
            )
        for item in _children(session, material_approval_analogs, row.id):
            session.execute(
                material_approval_analogs.insert().values(
                    id=str(uuid4()),
                    approval_id=record_id,
                    brand=item.brand,
                    manufacturer=item.manufacturer,
                    **base,
                )
            )
        for item in _children(session, material_approval_suppliers, row.id):
            session.execute(
                material_approval_suppliers.insert().values(
                    id=str(uuid4()),
                    approval_id=record_id,
                    supplier_name=item.supplier_name,
                    **base,
                )
            )
        for item in _steps(session, row.id):
            session.execute(
                material_approval_steps.insert().values(
                    id=str(uuid4()),
                    approval_id=record_id,
                    approver_user_id=item.approver_user_id,
                    step_order=item.step_order,
                    decision=None,
                    comment=None,
                    decided_at=None,
                    **base,
                )
            )
        for item in _children(session, material_approval_files, row.id):
            session.execute(
                material_approval_files.insert().values(
                    id=str(uuid4()),
                    file_id=str(uuid4()),
                    approval_id=record_id,
                    company_id=row.company_id,
                    project_id=row.project_id,
                    storage_key=item.storage_key,
                    sha256=item.sha256,
                    size=item.size,
                    content_type=item.content_type,
                    kind=item.kind,
                    created_by=user.id,
                    updated_by=user.id,
                    created_at=stamp,
                    updated_at=stamp,
                    row_version=1,
                    deleted_at=None,
                )
            )
        _cas(session, row.id, int(row.row_version), {}, updated_by=user.id)
        _audit(
            session,
            "submittal.version",
            record_id,
            row.project_id,
            {"version": int(row.version) + 1, "parent_id": row.id},
            company_id=row.company_id,
            actor_user_id=user.id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    finally:
        session.close()
    return _with_push(_saved(record_id, user.id))


def _duplicate_label(session, company_id: str, digest: str) -> str | None:
    found = session.execute(
        select(material_approvals.c.number)
        .select_from(material_approval_files.join(
            material_approvals, material_approvals.c.id == material_approval_files.c.approval_id
        ))
        .where(
            material_approval_files.c.company_id == company_id,
            material_approval_files.c.sha256 == digest,
            material_approval_files.c.deleted_at.is_(None),
        )
        .limit(1)
    ).first()
    if found is None:
        return None
    return DUPLICATE_WARNING.format(label=found[0])


def attach_file(
    user,
    access: dict,
    approval_id: str,
    file_id: str,
    raw: bytes,
    content_type: str | None,
    row_version: int,
    kind: str = "cert",
) -> dict:
    record_file = _uuid(file_id)
    if kind not in FILE_KINDS:
        raise HTTPException(status_code=400, detail="Некорректный тип файла")
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    try:
        if raw.startswith(b"%PDF") or declared == "application/pdf":
            cleaned = strip_pdf_author(raw)
            media_type = "application/pdf"
        else:
            cleaned, media_type, _suffix = strip_image(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    digest = hashlib.sha256(cleaned).hexdigest()
    storage_key = _storage_key()
    if record_file in storage_key or "/" in storage_key:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    try:
        occupied = resolve_stored_file("upload", storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор") from exc
    if occupied.exists():
        raise HTTPException(status_code=409, detail="Изменено другим")
    tmp = write_exclusive_temp("upload", cleaned)
    published = False
    warning = None
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        if (
            row is None
            or row.deleted_at
            or row.project_id != access["project_id"]
            or row.company_id != access["company_id"]
        ):
            raise HTTPException(status_code=404, detail="Не найдено")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        warning = _duplicate_label(session, row.company_id, digest)
        stamp = _now()
        session.execute(
            material_approval_files.insert().values(
                id=str(uuid4()),
                file_id=record_file,
                approval_id=approval_id,
                company_id=row.company_id,
                project_id=row.project_id,
                storage_key=storage_key,
                sha256=digest,
                size=len(cleaned),
                content_type=media_type,
                kind=kind,
                created_by=user.id,
                updated_by=user.id,
                created_at=stamp,
                updated_at=stamp,
                row_version=1,
                deleted_at=None,
            )
        )
        _cas(session, approval_id, int(row_version), {}, updated_by=user.id)
        _audit(
            session,
            "submittal.file",
            approval_id,
            row.project_id,
            {"file_id": record_file, "kind": kind},
            company_id=row.company_id,
            actor_user_id=user.id,
        )
        session.commit()
        publish_exclusive("upload", tmp, storage_key)
        published = True
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    except Exception:
        session.rollback()
        raise
    finally:
        if not published:
            discard_temp(tmp)
        session.close()
    data = _saved(approval_id, user.id)
    data["file_id"] = record_file
    data["duplicate_warning"] = warning
    return data


def set_price(user, approval_id: str, price: float, file_id: str, row_version: int) -> dict:
    if price <= 0:
        raise HTTPException(status_code=400, detail="Укажите цену")
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        stored = session.execute(
            select(material_approval_files).where(
                material_approval_files.c.approval_id == approval_id,
                material_approval_files.c.file_id == file_id,
                material_approval_files.c.deleted_at.is_(None),
            )
        ).mappings().first()
        if stored is None or stored.kind not in PRICE_KINDS:
            session.rollback()
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        _cas(
            session,
            approval_id,
            int(row_version),
            {"indicative_price": float(price), "price_file_id": file_id},
            updated_by=user.id,
        )
        _audit(
            session,
            "submittal.price",
            approval_id,
            row.project_id,
            {"price_file_id": file_id},
            company_id=row.company_id,
            actor_user_id=user.id,
        )
        session.commit()
    finally:
        session.close()
    return _saved(approval_id, user.id)


def read_file(project_id: str, approval_id: str, file_id: str):
    with store._sql.factory() as session:
        row = _load(session, approval_id)
        stored = None
        if row is not None:
            stored = session.execute(
                select(material_approval_files)
                .where(
                    material_approval_files.c.approval_id == approval_id,
                    material_approval_files.c.company_id == row.company_id,
                    material_approval_files.c.file_id == file_id,
                    material_approval_files.c.deleted_at.is_(None),
                )
                .order_by(material_approval_files.c.created_at)
            ).mappings().first()
    if row is None or row.deleted_at or row.project_id != project_id or stored is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    if file_id in str(stored.storage_key):
        raise HTTPException(status_code=404, detail="Не найдено")
    try:
        path = resolve_stored_file("upload", stored.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Не найдено") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Не найдено")
    return str(path), stored.content_type


def create_link(user, access: dict, approval_id: str, body: dict) -> dict:
    days = int(body.get("expires_in_days") or LINK_MIN_DAYS)
    if days < LINK_MIN_DAYS or days > LINK_MAX_DAYS:
        raise HTTPException(status_code=400, detail="Срок ссылки от 14 до 30 дней")
    link_id = _uuid(str(body.get("id") or ""))
    token = new_share_token()
    expires = datetime.now(UTC) + timedelta(days=days)
    stamp = _now()
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        if (
            row is None
            or row.deleted_at
            or row.project_id != access["project_id"]
            or row.company_id != access["company_id"]
            or row.status != "in_review"
        ):
            raise HTTPException(status_code=404 if row is None or row.deleted_at else 409, detail="Не найдено" if row is None else "Этот переход статуса недоступен")
        if row.status != "in_review":
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        session.execute(
            access_tokens.insert().values(
                id=link_id,
                company_id=access["company_id"],
                project_id=access["project_id"],
                purpose=PURPOSE,
                token_sha256=token_hash(token),
                entity_id=approval_id,
                expires_at=expires.isoformat(timespec="seconds"),
                used_at=None,
                created_by=user.id,
                updated_by=user.id,
                created_at=stamp,
                updated_at=stamp,
                row_version=1,
                deleted_at=None,
            )
        )
        _audit(
            session,
            "submittal.link",
            approval_id,
            access["project_id"],
            {"expires_in_days": days},
            company_id=access["company_id"],
            actor_user_id=user.id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    finally:
        session.close()
    return {"id": link_id, "token": token, "expires_at": expires.isoformat(timespec="seconds")}


def revoke_link(user, access: dict, approval_id: str, link_id: str) -> dict:
    stamp = _now()
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        link = session.execute(select(access_tokens).where(access_tokens.c.id == link_id)).mappings().first()
        if (
            row is None
            or row.deleted_at
            or link is None
            or link.entity_id != approval_id
            or link.purpose != PURPOSE
            or link.company_id != access["company_id"]
            or link.deleted_at
        ):
            raise HTTPException(status_code=404, detail="Не найдено")
        spent = session.execute(
            update(access_tokens)
            .where(
                access_tokens.c.id == link_id,
                access_tokens.c.row_version == int(link.row_version),
                access_tokens.c.deleted_at.is_(None),
            )
            .values(
                deleted_at=stamp,
                updated_at=stamp,
                updated_by=user.id,
                row_version=int(link.row_version) + 1,
            )
        )
        if spent.rowcount != 1:
            session.rollback()
            _conflict()
        _audit(
            session,
            "submittal.link_revoke",
            approval_id,
            row.project_id,
            {"link_id": link_id},
            company_id=row.company_id,
            actor_user_id=user.id,
        )
        session.commit()
    finally:
        session.close()
    return {"id": link_id, "revoked": True}


def _token_row(token: str):
    if not token or len(token) < 20:
        return None, 404
    digest = token_hash(token)
    with store._sql.factory() as session:
        rows = session.execute(
            select(access_tokens).where(
                access_tokens.c.token_sha256 == digest,
                access_tokens.c.purpose == PURPOSE,
            )
        ).mappings().all()
    match = next((row for row in rows if hashes_match(row.token_sha256, digest)), None)
    if match is None or match.deleted_at:
        return None, 404
    expires = parse_expiry(match.expires_at)
    if expires is None or expires <= datetime.now(UTC):
        return match, 410
    return match, None


def _public_or_error(token: str, *, writing: bool):
    from app.company_features import ensure_feature

    row, problem = _token_row(token)
    if problem == 404 or row is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    if problem == 410:
        raise HTTPException(status_code=410, detail="Срок ссылки истёк")
    if writing and row.used_at:
        raise HTTPException(status_code=410, detail="Срок ссылки истёк")
    try:
        ensure_feature(row.company_id, "submittals")
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="Ссылка не найдена") from exc
    return row


def public_read(token: str) -> dict:
    link = _public_or_error(token, writing=False)
    data = _saved(link.entity_id, "")
    return {
        "number": data["number"],
        "name": data["name"],
        "brand": data["brand"],
        "unit": data["unit"],
        "qty": data["qty"],
        "status": data["status"],
        "need_by": data["need_by"],
        "specs": data["specs"],
        "analogs": [{"brand": item["brand"]} for item in data["analogs"]],
        "overdue": data["overdue"],
        "budget_warning": data["budget_warning"],
        "decided": bool(link.used_at) or data["status"] not in {"draft", "in_review"},
        "row_version": data["row_version"],
    }


def public_decide(token: str, decision: str, comment: str) -> dict:
    link = _public_or_error(token, writing=True)
    data = set_status(
        None,
        link.entity_id,
        decision,
        _saved(link.entity_id, "")["row_version"],
        comment,
        token_id=link.id,
        token_version=int(link.row_version),
    )
    return {"status": data["status"], "push": data["push"]}


def _brand_key(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _allowed_brands(session, row) -> set[str]:
    brands = {_brand_key(row.brand)}
    for item in _children(session, material_approval_analogs, row.id):
        brands.add(_brand_key(item.brand))
    return {item for item in brands if item}


def approval_on_project(approval_id: str | None, project_id: str) -> bool:
    if not approval_id:
        return False
    try:
        with store._sql.factory() as session:
            row = _load(session, approval_id)
            return bool(row and not row.deleted_at and row.project_id == project_id)
    except (OperationalError, ProgrammingError):
        return False


def approval_still_valid(approval_id: str | None, project_id: str, brand: str = "") -> bool:
    if not approval_id:
        return False
    try:
        with store._sql.factory() as session:
            row = _load(session, approval_id)
            if row is None or row.deleted_at or row.project_id != project_id or row.status not in APPROVED:
                return False
            if brand and _brand_key(brand) not in _allowed_brands(session, row):
                return False
            return True
    except (OperationalError, ProgrammingError):
        return False


def line_order_blocked(project, line) -> bool:
    if not getattr(line, "requires_approval", False):
        return False
    company_id = project_company_id(project)
    if not feature_open_for_company(company_id, "submittals"):
        return False
    return not approval_still_valid(getattr(line, "approval_id", None), project.id, getattr(line, "brand", "") or "")


def annotate_sheet(store_obj, request, body: dict) -> dict:
    project = store_obj.get_project(request.project_id)
    if project is None:
        return body
    if not feature_open_for_company(project_company_id(project), "submittals"):
        return body
    for line in body.get("lines") or []:
        source = store_obj.proc_lines.get(line["id"])
        if source is None:
            continue
        if getattr(source, "requires_approval", False) and not approval_still_valid(
            getattr(source, "approval_id", None), project.id, getattr(source, "brand", "") or ""
        ):
            line["needs_approval"] = True
        allowed = set()
        approval_id = getattr(source, "approval_id", None)
        if approval_id and approval_still_valid(approval_id, project.id):
            with store._sql.factory() as session:
                row = _load(session, approval_id)
                if row is not None:
                    allowed = _allowed_brands(session, row)
        for offer in line.get("offers") or []:
            raw = store_obj.proc_offers.get(offer["id"])
            offered = _brand_key(getattr(raw, "offered_brand", "") or "")
            if offered and offered not in allowed:
                offer["unapproved_brand"] = True
                offer["offered_brand"] = raw.offered_brand
        for cell in (line.get("cells") or {}).values():
            if not cell:
                continue
            match = next((item for item in line["offers"] if item["id"] == cell["id"] and item.get("unapproved_brand")), None)
            if match:
                cell["unapproved_brand"] = True
                cell["offered_brand"] = match.get("offered_brand")
    return body


def mark_mismatch(user, approval_id: str, brand: str, row_version: int) -> dict:
    offered = _text(brand, 200, required=True)
    session = store._sql.factory()
    try:
        row = _load(session, approval_id)
        if row is None or row.deleted_at or row.status not in APPROVED:
            raise HTTPException(status_code=404, detail="Не найдено")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        if _brand_key(offered) in _allowed_brands(session, row):
            session.rollback()
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        _audit(
            session,
            "submittal.mismatch",
            approval_id,
            row.project_id,
            {"status": row.status},
            company_id=row.company_id,
            actor_user_id=user.id,
        )
        session.commit()
        project_id = row.project_id
    finally:
        session.close()
    punch = store.add_punch(project_id, {"title": "mismatch", "location": approval_id, "trade": "materials"})
    return {"punch_id": punch.id, "approval_id": approval_id, "push": push_payload(approval_id)}


def render_pdf(user, approval_id: str) -> bytes:
    data = read_for_user(user, approval_id)
    lines = [data["number"], data["status"], data["need_by"] or "", data["name"], data["brand"], data["unit"]]
    font = ImageFont.truetype(_FONT, 22)
    image = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(image)
    y = 48
    for line in lines:
        draw.text((48, y), str(line)[:80], fill="black", font=font)
        y += 36
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    jpeg = out.getvalue()
    width, height = image.size
    content = f"q {width} 0 0 {height} 0 0 cm /Im Do Q".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Contents 4 0 R /Resources << /XObject << /Im 5 0 R >> >> >>"
        ).encode("ascii"),
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream",
        (
            b"<< /Type /XObject /Subtype /Image /ColorSpace /DeviceRGB /BitsPerComponent 8 "
            + f"/Width {width} /Height {height} /Filter /DCTDecode /Length {len(jpeg)}".encode("ascii")
            + b" >>\nstream\n"
            + jpeg
            + b"\nendstream"
        ),
        b"<< /Author () /Creator () /Producer () /Title () >>",
    ]
    blob = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(blob))
        blob.extend(f"{index} 0 obj\n".encode("ascii"))
        blob.extend(obj)
        blob.extend(b"\nendobj\n")
    xref = len(blob)
    blob.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    blob.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        blob.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    blob.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(blob)
