"""Completed-work acts and the cost certificate computed from them.

Company id comes from the project. Access is one join: no row means 404.
Totals, VAT and line amounts are recomputed here. Client totals are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, text, true, update
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import aliased

from app.audit import write as audit_write
from app.company_features import ensure_feature, resolve_path_company
from app.ks_export import (
    ks2_lines,
    ks2_rows,
    ks3_lines,
    ks3_rows,
    render_pdf,
    render_xlsx,
)
from app.ks_files import discard_temp, prepare_pdf, publish_pdf
from app.ks_schema import KsAct, KsActLine
from app.schemas import User
from app.site_models import Project
from app.sql_backend import Record
from app.store import store
from app.tax import lookup_vat
from app.tenant import company_key

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DRAFT = {"owner", "foreman", "supervisor"}
_MONEY = {"owner", "supervisor"}
_KNOWN = {"owner", "foreman", "supervisor", "procurement", "customer", "supplier", "moderator"}
_RANK = {"draft": 0, "submitted": 1, "signed": 2, "rejected": 3, "cancelled": 4}
_REASONS = {"qty_mismatch", "price_mismatch", "period_mismatch", "docs_missing", "other"}
_Q = Decimal("0.001")


class KsError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass
class Access:
    user: User
    project: Project
    company_id: str
    act: dict | None = None


def _stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def q3(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_Q, rounding=ROUND_HALF_UP)


def tiyn_to_kzt(tiyn: int) -> int:
    return int((Decimal(int(tiyn)) / Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def amount_tiyn(qty: Decimal, price: int) -> int:
    raw = (q3(qty) * Decimal(int(price))).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if raw < 0:
        raise KsError(422, "invalid_amount")
    return int(raw)


def vat_of(total: int, rate_bp: int) -> int:
    raw = (Decimal(int(total)) * Decimal(int(rate_bp)) / Decimal(10000)).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return int(raw)


def _uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError) as exc:
        raise KsError(422, "invalid_id") from exc


def _day(value: str) -> str:
    raw = str(value or "").strip()
    if not _DATE.match(raw):
        raise KsError(422, "invalid_date")
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise KsError(422, "invalid_date") from exc
    return raw


def _roles(user: User, project: Project) -> set[str]:
    found: set[str] = set()
    if project.owner_id == user.id:
        found.add("owner")
    member = False
    for row in store.directory.values():
        if row.project_id != project.id or row.user_id != user.id:
            continue
        member = True
        label = (row.role_on_site or "").strip().lower()
        if label in _KNOWN:
            found.add(label)
    if member and user.role in _KNOWN:
        found.add(user.role)
    return found


def _need(user: User, project: Project, allowed: set[str]) -> None:
    if not (_roles(user, project) & allowed):
        raise KsError(403, "forbidden")


def _open_access(project, user: User):
    member = aliased(Record)
    access = or_(
        member.user_id == user.id,
        project.owner_id == user.id,
        project.company_key == company_key(user),
    )
    if user.role == "admin":
        access = true()
    return member, access


def access_project(pid: str, user: User) -> Access:
    company_id = resolve_path_company("projects", pid, user)
    if not company_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    project = store.get_project(pid)
    if project is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    ensure_feature(company_id, "ks_acts")
    return Access(user=user, project=project, company_id=company_id)


def access_act(act_id: str, user: User) -> Access:
    if not _UUID.match(str(act_id or "")):
        raise HTTPException(status_code=404, detail="Не найдено")
    project = aliased(Record)
    member, access = _open_access(project, user)
    stmt = (
        select(KsAct, project.owner_id, project.payload)
        .join(project, and_(project.collection == "projects", project.doc_id == KsAct.project_id))
        .outerjoin(
            member,
            and_(
                member.collection == "directory",
                member.project_id == project.doc_id,
                member.user_id == user.id,
            ),
        )
        .where(KsAct.id == act_id, KsAct.deleted_at.is_(None), access)
        .limit(1)
    )
    with store._sql.factory() as session:
        found = session.execute(stmt).first()
        if found is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        row, owner_id, payload = found
        lines = session.scalars(
            select(KsActLine)
            .where(KsActLine.act_id == row.id, KsActLine.deleted_at.is_(None))
            .order_by(KsActLine.line_no)
        ).all()
        public = _public(row, lines)
    owner = store.get_user(str(owner_id or ""))
    company_id = company_key(owner) if owner is not None else ""
    if not company_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    ensure_feature(company_id, "ks_acts")
    item = Access(user=user, project=Project.model_validate(payload), company_id=company_id)
    item.act = public
    return item


def _qty(value) -> str:
    return format(q3(Decimal(str(value or 0))), "f")


def _line_public(row: KsActLine) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "act_id": row.act_id,
        "line_no": int(row.line_no),
        "estimate_line_id": row.estimate_line_id,
        "change_order_line_id": row.change_order_line_id,
        "name": row.name,
        "unit": row.unit,
        "qty_contract": _qty(row.qty_contract),
        "qty_prev": _qty(row.qty_prev),
        "qty_period": _qty(row.qty_period),
        "unit_price_tiyn": int(row.unit_price_tiyn),
        "amount_tiyn": int(row.amount_tiyn),
        "over_contract": bool(row.over_contract),
        "row_version": int(row.row_version),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "deleted_at": row.deleted_at,
    }


def _public(row: KsAct, lines: list[KsActLine]) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "contract_ref": row.contract_ref,
        "number": int(row.number),
        "act_date": row.act_date,
        "period_from": row.period_from,
        "period_to": row.period_to,
        "status": row.status,
        "reject_reason_code": row.reject_reason_code,
        "total_tiyn": int(row.total_tiyn),
        "vat_tiyn": int(row.vat_tiyn),
        "total_with_vat_tiyn": int(row.total_with_vat_tiyn),
        "vat_rate_bp": int(row.vat_rate_bp),
        "vat_rate_id": row.vat_rate_id,
        "currency": row.currency,
        "signed_file_id": row.signed_file_id,
        "signed_at": row.signed_at,
        "submitted_at": row.submitted_at,
        "budget_fact_written_at": row.budget_fact_written_at,
        "esf_status": row.esf_status,
        "row_version": int(row.row_version),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "deleted_at": row.deleted_at,
        "lines": [_line_public(line) for line in lines],
    }


def _summary(row: KsAct) -> dict:
    data = _public(row, [])
    data.pop("lines")
    return data


def _audit(session, action: str, act: KsAct, user: User, changes: dict) -> None:
    audit_write(
        action,
        "ks_act",
        act.id,
        act.project_id,
        changes,
        session=session,
        company_id=act.company_id,
        actor_user_id=user.id,
    )


def _cas(session, act: KsAct, user: User, values: dict) -> None:
    version = int(act.row_version)
    values = {
        **values,
        "row_version": version + 1,
        "updated_at": _stamp(),
        "updated_by": user.id,
    }
    result = session.execute(
        update(KsAct).where(KsAct.id == act.id, KsAct.row_version == version).values(**values)
    )
    if result.rowcount != 1:
        raise KsError(409, "row_version")
    for key, value in values.items():
        setattr(act, key, value)


def _alloc(session, company_id: str, project_id: str, stamp: str) -> int:
    session.execute(
        text(
            """
            INSERT INTO ks_act_counters (company_id, project_id, next_no, updated_at)
            VALUES (:company_id, :project_id, 1, :stamp)
            ON CONFLICT (company_id, project_id) DO NOTHING
            """
        ),
        {"company_id": company_id, "project_id": project_id, "stamp": stamp},
    )
    number = session.execute(
        text(
            """
            UPDATE ks_act_counters
            SET next_no = next_no + 1, updated_at = :stamp
            WHERE company_id = :company_id AND project_id = :project_id
            RETURNING next_no - 1
            """
        ),
        {"company_id": company_id, "project_id": project_id, "stamp": stamp},
    ).scalar_one()
    return int(number)


def _norm_line(item: dict) -> dict | None:
    name = str(item.get("name") or item.get("title") or "").strip()[:500]
    if not name:
        return None
    unit = str(item.get("unit") or "pcs").strip()[:20] or "pcs"
    try:
        qty = q3(Decimal(str(item.get("qty") if item.get("qty") is not None else item.get("qty_contract") or 0)))
    except (InvalidOperation, ValueError) as exc:
        raise KsError(422, "invalid_qty") from exc
    if item.get("unit_price_tiyn") is not None:
        price = int(item["unit_price_tiyn"])
    else:
        price = int(item.get("unit_price_kzt") or 0) * 100
    if qty < 0 or price < 0:
        raise KsError(422, "invalid_amount")
    line_id = str(item.get("id") or item.get("estimate_line_id") or "")[:80] or None
    return {
        "estimate_line_id": line_id,
        "name": name,
        "unit": unit,
        "qty_contract": qty,
        "unit_price_tiyn": price,
    }


def estimate_lines(project_id: str) -> list[dict]:
    found: list[dict] = []
    with store._sql.factory() as session:
        rows = session.scalars(
            select(Record).where(Record.collection == "estimates", Record.project_id == project_id)
        ).all()
    for row in rows:
        payload = row.payload or {}
        for item in payload.get("lines") or []:
            if isinstance(item, dict):
                norm = _norm_line(item)
                if norm:
                    found.append(norm)
    if found:
        return found
    for item in store.budget_lines.values():
        if item.project_id != project_id:
            continue
        norm = _norm_line(
            {
                "id": item.id,
                "title": item.title,
                "unit": "pcs",
                "qty": "1.000",
                "unit_price_kzt": item.budget_kzt,
            }
        )
        if norm:
            found.append(norm)
    return found


def _qty_prev(session, project_id: str, estimate_line_id: str | None, period_from: str) -> Decimal:
    if not estimate_line_id:
        return Decimal("0.000")
    total = session.execute(
        text(
            """
            SELECT COALESCE(SUM(l.qty_period), 0)
            FROM ks_act_lines l
            JOIN ks_acts a ON a.id = l.act_id
            WHERE a.project_id = :project_id
              AND a.status = 'signed'
              AND a.deleted_at IS NULL
              AND l.deleted_at IS NULL
              AND l.estimate_line_id = :line_id
              AND a.period_to < :period_from
            """
        ),
        {"project_id": project_id, "line_id": estimate_line_id, "period_from": period_from},
    ).scalar()
    return q3(Decimal(str(total or 0)))


def _totals(lines: list[KsActLine], rate_bp: int) -> tuple[int, int, int]:
    total = sum(int(line.amount_tiyn) for line in lines)
    vat = vat_of(total, rate_bp)
    return total, vat, total + vat


def _reload(session, act_id: str) -> dict:
    row = session.get(KsAct, act_id)
    lines = session.scalars(
        select(KsActLine).where(KsActLine.act_id == act_id, KsActLine.deleted_at.is_(None)).order_by(KsActLine.line_no)
    ).all()
    return _public(row, list(lines))


def list_acts(project_id: str) -> list[dict]:
    try:
        with store._sql.factory() as session:
            rows = session.scalars(
                select(KsAct)
                .where(KsAct.project_id == project_id, KsAct.deleted_at.is_(None))
                .order_by(KsAct.number.desc())
            ).all()
            return [_summary(row) for row in rows]
    except (OperationalError, ProgrammingError):
        return []


def signed_works_kzt(project_id: str | None) -> int:
    if not project_id:
        return 0
    try:
        with store._sql.factory() as session:
            total = session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(total_with_vat_tiyn), 0)
                    FROM ks_acts
                    WHERE project_id = :project_id
                      AND status = 'signed'
                      AND deleted_at IS NULL
                      AND budget_fact_written_at IS NOT NULL
                    """
                ),
                {"project_id": project_id},
            ).scalar()
    except (OperationalError, ProgrammingError):
        return 0
    return tiyn_to_kzt(int(total or 0))


def create_draft(access: Access, body: dict) -> dict:
    _need(access.user, access.project, _DRAFT)
    act_id = _uuid(str(body.get("id") or ""))
    act_date = _day(str(body.get("act_date") or ""))
    period_from = _day(str(body.get("period_from") or ""))
    period_to = _day(str(body.get("period_to") or ""))
    if period_to < period_from:
        raise KsError(422, "invalid_period")
    contract = str(body.get("contract_ref") or "").strip()
    if len(contract) > 120:
        raise KsError(422, "invalid_contract")
    contract_ref = contract or None
    sources = estimate_lines(access.project.id)
    if not sources:
        raise KsError(422, "estimate_missing")
    stamp = _stamp()
    user = access.user
    try:
        with store._sql.factory() as session:
            try:
                rate_id, rate_bp, _basis = lookup_vat(session, act_date)
            except ValueError as exc:
                raise KsError(422, "vat_missing") from exc
            number = _alloc(session, access.company_id, access.project.id, stamp)
            act = KsAct(
                id=act_id,
                company_id=access.company_id,
                project_id=access.project.id,
                contract_ref=contract_ref,
                contract_ref_key=contract,
                number=number,
                act_date=act_date,
                period_from=period_from,
                period_to=period_to,
                status="draft",
                total_tiyn=0,
                vat_tiyn=0,
                total_with_vat_tiyn=0,
                vat_rate_bp=rate_bp,
                vat_rate_id=rate_id,
                currency="KZT",
                created_at=stamp,
                updated_at=stamp,
                created_by=user.id,
                updated_by=user.id,
                row_version=1,
            )
            session.add(act)
            built: list[KsActLine] = []
            for index, source in enumerate(sources, start=1):
                prev = _qty_prev(session, access.project.id, source["estimate_line_id"], period_from)
                line = KsActLine(
                    id=str(uuid4()),
                    company_id=access.company_id,
                    project_id=access.project.id,
                    act_id=act_id,
                    line_no=index,
                    estimate_line_id=source["estimate_line_id"],
                    change_order_line_id=None,
                    name=source["name"],
                    unit=source["unit"],
                    qty_contract=source["qty_contract"],
                    qty_prev=prev,
                    qty_period=Decimal("0.000"),
                    unit_price_tiyn=source["unit_price_tiyn"],
                    amount_tiyn=0,
                    over_contract=prev > source["qty_contract"],
                    created_at=stamp,
                    updated_at=stamp,
                    created_by=user.id,
                    updated_by=user.id,
                    row_version=1,
                )
                session.add(line)
                built.append(line)
            total, vat, gross = _totals(built, rate_bp)
            act.total_tiyn = total
            act.vat_tiyn = vat
            act.total_with_vat_tiyn = gross
            _audit(
                session,
                "act.create",
                act,
                user,
                {
                    "number": [0, number],
                    "total_tiyn": [0, total],
                    "vat_tiyn": [0, vat],
                    "total_with_vat_tiyn": [0, gross],
                    "vat_rate_bp": [0, rate_bp],
                },
            )
            session.commit()
            return _reload(session, act_id)
    except IntegrityError as exc:
        raise KsError(409, "period_taken") from exc


def update_lines(access: Access, body: dict) -> dict:
    _need(access.user, access.project, _DRAFT)
    current = access.act or {}
    if current.get("status") == "signed":
        raise KsError(409, "immutable")
    if current.get("status") != "draft":
        raise KsError(409, "invalid_status")
    expected = int(body.get("row_version") or 0)
    if expected != int(current["row_version"]):
        raise KsError(409, "row_version")
    patches = body.get("lines") or []
    if not isinstance(patches, list) or len(patches) > 500:
        raise KsError(422, "invalid_lines")
    by_id = {str(item.get("id")): item for item in patches if isinstance(item, dict)}
    stamp = _stamp()
    user = access.user
    changes: list[dict] = []
    with store._sql.factory() as session:
        act = session.get(KsAct, current["id"])
        if act is None or act.deleted_at or int(act.row_version) != expected:
            raise KsError(409, "row_version")
        if act.status != "draft":
            raise KsError(409, "immutable" if act.status == "signed" else "invalid_status")
        lines = list(
            session.scalars(
                select(KsActLine)
                .where(KsActLine.act_id == act.id, KsActLine.deleted_at.is_(None))
                .order_by(KsActLine.line_no)
            ).all()
        )
        known = {line.id for line in lines}
        if any(key not in known for key in by_id):
            raise KsError(422, "invalid_lines")
        for line in lines:
            patch = by_id.get(line.id)
            if patch is None:
                continue
            try:
                qty = q3(Decimal(str(patch.get("qty_period"))))
            except (InvalidOperation, ValueError) as exc:
                raise KsError(422, "invalid_qty") from exc
            if qty < 0:
                raise KsError(422, "invalid_qty")
            old_qty = q3(Decimal(str(line.qty_period)))
            old_amount = int(line.amount_tiyn)
            new_amount = amount_tiyn(qty, int(line.unit_price_tiyn))
            prev = q3(Decimal(str(line.qty_prev)))
            contract = q3(Decimal(str(line.qty_contract)))
            over = prev + qty > contract
            version = int(line.row_version)
            result = session.execute(
                update(KsActLine)
                .where(KsActLine.id == line.id, KsActLine.row_version == version)
                .values(
                    qty_period=qty,
                    amount_tiyn=new_amount,
                    over_contract=over,
                    row_version=version + 1,
                    updated_at=stamp,
                    updated_by=user.id,
                )
            )
            if result.rowcount != 1:
                raise KsError(409, "row_version")
            line.qty_period = qty
            line.amount_tiyn = new_amount
            line.over_contract = over
            line.row_version = version + 1
            changes.append(
                {
                    "line_no": int(line.line_no),
                    "qty_period_milli": [int(old_qty * 1000), int(qty * 1000)],
                    "amount_tiyn": [old_amount, new_amount],
                }
            )
        total, vat, gross = _totals(lines, int(act.vat_rate_bp))
        old_total = int(act.total_tiyn)
        old_vat = int(act.vat_tiyn)
        _cas(
            session,
            act,
            user,
            {"total_tiyn": total, "vat_tiyn": vat, "total_with_vat_tiyn": gross},
        )
        _audit(
            session,
            "act.line_update",
            act,
            user,
            {"total_tiyn": [old_total, total], "vat_tiyn": [old_vat, vat], "lines": changes},
        )
        session.commit()
        return _reload(session, act.id)


def _move(access: Access, row_version: int, target: str, allowed_from: set[str], action: str, extra: dict | None = None) -> dict:
    current = access.act or {}
    if int(current.get("row_version") or 0) != int(row_version):
        raise KsError(409, "row_version")
    status = str(current.get("status") or "")
    if status == "signed" and target != "signed":
        raise KsError(409, "immutable")
    if status not in allowed_from:
        raise KsError(409, "invalid_status")
    user = access.user
    values = {"status": target, **(extra or {})}
    with store._sql.factory() as session:
        act = session.get(KsAct, current["id"])
        if act is None or int(act.row_version) != int(row_version):
            raise KsError(409, "row_version")
        if act.status not in allowed_from:
            raise KsError(409, "immutable" if act.status == "signed" else "invalid_status")
        old = _RANK.get(act.status, 0)
        _cas(session, act, user, values)
        _audit(session, action, act, user, {"status_rank": [old, _RANK[target]]})
        session.commit()
        return _reload(session, act.id)


def submit_act(access: Access, row_version: int) -> dict:
    _need(access.user, access.project, _MONEY)
    return _move(access, row_version, "submitted", {"draft"}, "act.submit", {"submitted_at": _stamp()})


def reject_act(access: Access, row_version: int, reason: str) -> dict:
    _need(access.user, access.project, _MONEY)
    code = str(reason or "").strip()
    if code not in _REASONS:
        raise KsError(422, "invalid_reason")
    return _move(
        access,
        row_version,
        "rejected",
        {"submitted"},
        "act.reject",
        {"reject_reason_code": code},
    )


def cancel_act(access: Access, row_version: int) -> dict:
    _need(access.user, access.project, _MONEY)
    return _move(access, row_version, "cancelled", {"draft", "rejected"}, "act.cancel")


def reopen_act(access: Access, row_version: int) -> dict:
    _need(access.user, access.project, _DRAFT)
    return _move(access, row_version, "draft", {"rejected"}, "act.create", {"reject_reason_code": None})


def sign_act(access: Access, row_version: int, raw: bytes) -> dict:
    _need(access.user, access.project, _MONEY)
    current = access.act or {}
    if current.get("status") == "signed" and current.get("budget_fact_written_at"):
        return current
    if current.get("status") != "submitted":
        raise KsError(409, "invalid_status")
    if int(current.get("row_version") or 0) != int(row_version):
        raise KsError(409, "row_version")
    staged = prepare_pdf(access.company_id, raw)
    file_id = staged["file_id"] or str(uuid4())
    stamp = _stamp()
    user = access.user
    try:
        with store._sql.factory() as session:
            act = session.get(KsAct, current["id"])
            if act is None:
                raise HTTPException(status_code=404, detail="Не найдено")
            if act.status == "signed" and act.budget_fact_written_at:
                return _reload(session, act.id)
            if act.status != "submitted":
                raise KsError(409, "invalid_status")
            if int(act.row_version) != int(row_version):
                raise KsError(409, "row_version")
            old_total = int(act.total_with_vat_tiyn)
            _cas(
                session,
                act,
                user,
                {
                    "status": "signed",
                    "signed_at": stamp,
                    "signed_file_id": file_id,
                    "budget_fact_written_at": stamp,
                },
            )
            _audit(
                session,
                "act.sign",
                act,
                user,
                {
                    "status_rank": [_RANK["submitted"], _RANK["signed"]],
                    "total_with_vat_tiyn": [old_total, old_total],
                },
            )
            session.commit()
            saved = _reload(session, act.id)
    except Exception:
        discard_temp(staged)
        raise
    publish_pdf(staged, user, access.project.id, file_id)
    return saved


def ks3_report(access: Access, period_from: str, period_to: str) -> dict:
    start = _day(period_from)
    end = _day(period_to)
    if end < start:
        raise KsError(422, "invalid_period")
    year_start = f"{end[:4]}-01-01"
    with store._sql.factory() as session:
        rows = session.scalars(
            select(KsAct).where(
                KsAct.project_id == access.project.id,
                KsAct.company_id == access.company_id,
                KsAct.status == "signed",
                KsAct.deleted_at.is_(None),
            )
        ).all()
    period = [row for row in rows if not (row.period_to < start or row.period_from > end)]
    year = [row for row in rows if year_start <= row.act_date <= end]
    opened = [row for row in rows if row.act_date <= end]

    def pack(items: list[KsAct]) -> tuple[int, int, int]:
        total = sum(int(item.total_tiyn) for item in items)
        vat = sum(int(item.vat_tiyn) for item in items)
        gross = sum(int(item.total_with_vat_tiyn) for item in items)
        return total, vat, gross

    period_total, period_vat, period_gross = pack(period)
    year_total, _year_vat, _year_gross = pack(year)
    start_total, _start_vat, _start_gross = pack(opened)
    return {
        "project_id": access.project.id,
        "period_from": start,
        "period_to": end,
        "period_tiyn": period_total,
        "period_vat_tiyn": period_vat,
        "period_with_vat_tiyn": period_gross,
        "year_tiyn": year_total,
        "start_tiyn": start_total,
        "act_ids": [row.id for row in period],
    }


def export_ks2(access: Access, kind: str) -> tuple[bytes, str, str]:
    act = access.act
    if act is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    number = int(act["number"])
    if kind == "pdf":
        return render_pdf(ks2_lines(act)), "application/pdf", f"ks2-{number}.pdf"
    return render_xlsx(ks2_rows(act)), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"ks2-{number}.xlsx"


def export_ks3(access: Access, period_from: str, period_to: str, kind: str) -> tuple[bytes, str, str]:
    report = ks3_report(access, period_from, period_to)
    if kind == "pdf":
        return render_pdf(ks3_lines(report)), "application/pdf", "ks3.pdf"
    return (
        render_xlsx(ks3_rows(report)),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ks3.xlsx",
    )

