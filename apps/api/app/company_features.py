"""Company feature flags and append-only audit events."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import demo_mode
from app.deps import require_user
from app.schemas import User
from app.sql_backend import AuditLog, CompanyFeature
from app.store import store

FEATURE_KEYS: tuple[str, ...] = (
    "drawings",
    "punch_photos",
    "checklists",
    "rfi",
    "submittals",
    "submittals_procurement",
    "changes",
    "subcontracts",
    "gantt",
    "meetings",
    "offline",
)

_ITEM_ATTR = {
    "rfi": ("rfis", "rid"),
    "checklists": ("inspections", "iid"),
    "meetings": ("meetings", "mid"),
    "gantt": ("schedule", "tid"),
    "changes": ("change_orders", "cid"),
    "drawings": ("drawings", "did"),
    "submittals": ("submittals", "sid"),
}

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_BIN = re.compile(r"^bin:\d{12}$")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def company_id_of(user: User) -> str:
    """Tenant id until a companies table exists. Never the name: form."""
    digits = re.sub(r"\D", "", user.company_bin or "")
    if len(digits) == 12:
        return f"bin:{digits}"
    return f"user:{user.id}"


def member_of(user: User, company_id: str) -> bool:
    return bool(company_id) and company_id_of(user) == company_id and not company_id.startswith("name:")


def project_company_id(project) -> str:
    owner_id = getattr(project, "owner_id", None)
    if not owner_id:
        return ""
    owner = store.get_user(owner_id)
    if owner is None:
        return ""
    return company_id_of(owner)


def _live(row: CompanyFeature | None) -> CompanyFeature | None:
    if row is None or row.deleted_at:
        return None
    return row


def _rows(company_id: str) -> dict[str, CompanyFeature]:
    with store._sql.factory() as session:
        found = session.scalars(select(CompanyFeature).where(CompanyFeature.company_id == company_id)).all()
        return {row.key: row for row in found if _live(row) is not None}


def flag_map(company_id: str) -> dict[str, bool]:
    stored = _rows(company_id) if company_id else {}
    return {key: bool(stored[key].enabled) if key in stored else False for key in FEATURE_KEYS}


def feature_open_for_company(company_id: str, key: str) -> bool:
    if key not in FEATURE_KEYS:
        return False
    if demo_mode():
        return True
    return flag_map(company_id).get(key, False)


def _public(company_id: str, key: str, row: CompanyFeature | None) -> dict:
    live = _live(row)
    if live is None:
        return {
            "id": None,
            "company_id": company_id,
            "key": key,
            "enabled": False,
            "changed_by": "",
            "changed_at": "",
            "row_version": 0,
            "updated_at": "",
            "deleted_at": None,
        }
    return {
        "id": live.id,
        "company_id": live.company_id,
        "key": live.key,
        "enabled": bool(live.enabled),
        "changed_by": live.changed_by,
        "changed_at": live.changed_at,
        "row_version": int(live.row_version),
        "updated_at": live.updated_at,
        "deleted_at": live.deleted_at,
    }


def list_features(company_id: str) -> list[dict]:
    stored = _rows(company_id)
    return [_public(company_id, key, stored.get(key)) for key in FEATURE_KEYS]


def _audit(company_id: str, key: str, enabled: bool, actor: str, stamp: str) -> AuditLog:
    return AuditLog(
        event="feature.enable" if enabled else "feature.disable",
        company_id=company_id,
        actor=actor,
        at=stamp,
        key=key,
    )


def set_feature(
    company_id: str,
    key: str,
    enabled: bool,
    actor: str,
    *,
    row_version: int | None,
    record_id: str | None = None,
) -> dict:
    if key not in FEATURE_KEYS:
        raise HTTPException(status_code=400, detail="Неизвестный ключ")
    assert_bin_or_user(company_id)
    if record_id is not None and not _UUID.match(record_id):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    stamp = _now()
    with store._sql.factory() as session:
        current = session.scalar(
            select(CompanyFeature).where(CompanyFeature.company_id == company_id, CompanyFeature.key == key)
        )
        if current is None:
            if row_version not in (None, 0):
                raise HTTPException(status_code=409, detail="Изменено другим")
            row = CompanyFeature(
                id=record_id or str(uuid4()),
                company_id=company_id,
                key=key,
                enabled=enabled,
                changed_by=actor,
                changed_at=stamp,
                row_version=1,
                updated_at=stamp,
                deleted_at=None,
            )
            session.add(row)
            session.add(_audit(company_id, key, enabled, actor, stamp))
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise HTTPException(status_code=409, detail="Изменено другим") from exc
            return _public(company_id, key, row)
        tombstone = current.deleted_at is not None
        if tombstone:
            if row_version not in (None, 0) and row_version != current.row_version:
                raise HTTPException(status_code=409, detail="Изменено другим")
        elif row_version != current.row_version:
            raise HTTPException(status_code=409, detail="Изменено другим")
        new_version = int(current.row_version) + 1
        result = session.execute(
            update(CompanyFeature)
            .where(CompanyFeature.id == current.id, CompanyFeature.row_version == current.row_version)
            .values(
                enabled=enabled,
                changed_by=actor,
                changed_at=stamp,
                updated_at=stamp,
                row_version=new_version,
                deleted_at=None,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(status_code=409, detail="Изменено другим")
        session.add(_audit(company_id, key, enabled, actor, stamp))
        session.commit()
        current.enabled = enabled
        current.changed_by = actor
        current.changed_at = stamp
        current.updated_at = stamp
        current.row_version = new_version
        current.deleted_at = None
        return _public(company_id, key, current)


def audit_events(company_id: str) -> list[dict]:
    with store._sql.factory() as session:
        rows = session.scalars(select(AuditLog).where(AuditLog.company_id == company_id).order_by(AuditLog.id)).all()
        return [
            {
                "id": row.id,
                "event": row.event,
                "company_id": row.company_id,
                "actor": row.actor,
                "at": row.at,
                "key": row.key,
            }
            for row in rows
        ]


def _without_photo(item):
    if hasattr(item, "model_dump"):
        data = item.model_dump()
    else:
        data = dict(item)
    data["photo"] = ""
    return data


def apply_bundle_flags(project, data: dict) -> dict:
    """Drop feature payloads the company has not turned on."""
    company_id = project_company_id(project)
    opened = {key: feature_open_for_company(company_id, key) for key in FEATURE_KEYS}
    if not opened["drawings"]:
        data["drawings"] = []
    if not opened["rfi"]:
        data["rfis"] = []
    if not opened["submittals"]:
        data["submittals"] = []
    if not opened["checklists"]:
        data["inspections"] = []
    if not opened["gantt"]:
        data["schedule"] = []
    if not opened["meetings"]:
        data["meetings"] = []
    if not opened["changes"]:
        data["changes"] = []
    if not opened["punch_photos"]:
        data["punches"] = [_without_photo(item) for item in data["punches"]]
    data["features"] = flag_map(company_id)
    data["company_id"] = company_id
    return data


def _company_from_route(key: str, values: dict[str, str | None]) -> str | None:
    pid = values.get("pid")
    if pid:
        project = store.get_project(pid)
        if project is not None:
            return project_company_id(project) or None
    attr = _ITEM_ATTR.get(key)
    if not attr:
        return None
    table_name, param = attr
    item_id = values.get(param)
    if not item_id:
        return None
    table = getattr(store, table_name, None)
    item = table.get(item_id) if isinstance(table, dict) else None
    if item is None:
        return None
    project = store.get_project(getattr(item, "project_id", ""))
    if project is None:
        return None
    return project_company_id(project) or None


def ensure_feature(company_id: str, key: str) -> None:
    if not feature_open_for_company(company_id, key):
        raise HTTPException(status_code=404, detail="Не найдено")


def require_feature(key: str):
    """Hide a route when the company flag is off. A missing flag is 404."""

    if key not in FEATURE_KEYS:
        raise RuntimeError(f"unknown feature {key}")

    def dependency(
        user: User = Depends(require_user),
        pid: str | None = None,
        rid: str | None = None,
        tid: str | None = None,
        cid: str | None = None,
        iid: str | None = None,
        did: str | None = None,
        sid: str | None = None,
        mid: str | None = None,
    ) -> User:
        company_id = _company_from_route(
            key,
            {"pid": pid, "rid": rid, "tid": tid, "cid": cid, "iid": iid, "did": did, "sid": sid, "mid": mid},
        )
        if not company_id:
            company_id = company_id_of(user)
        ensure_feature(company_id, key)
        return user

    return dependency


def assert_bin_or_user(company_id: str) -> None:
    if company_id.startswith("name:") or not (_BIN.match(company_id) or company_id.startswith("user:")):
        raise HTTPException(status_code=404, detail="Не найдено")
