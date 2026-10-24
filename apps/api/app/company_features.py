"""Company feature flags. require_feature reads ids from the path only."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from sqlalchemy import and_, case, inspect, or_, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.audit import write as audit_write
from app.config import demo_mode
from app.deps import require_user
from app.pf0_tables import AuditLog, CompanyFeature
from app.schemas import User
from app.sql_backend import Record
from app.store import store
from app.tenant import company_key

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

_PATH_IDS = (
    ("rid", "rfis"),
    ("tid", "schedule"),
    ("cid", "change_orders"),
    ("iid", "inspections"),
    ("did", "drawings"),
    ("sid", "submittals"),
    ("mid", "meetings"),
    ("pid", "projects"),
)

_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_BIN = re.compile(r"^bin:\d{12}$")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def company_id_of(user: User) -> str:
    """Stored tenant key. Profile BIN and company name are not read."""
    return company_key(user)


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


def _table_ready(name: str) -> bool:
    return inspect(store._sql.engine).has_table(name)


def _live(row: CompanyFeature | None) -> CompanyFeature | None:
    if row is None or row.deleted_at:
        return None
    return row


def _rows(company_id: str) -> dict[str, CompanyFeature]:
    if not company_id or not _table_ready("company_features"):
        return {}
    with store._sql.factory() as session:
        found = session.scalars(select(CompanyFeature).where(CompanyFeature.company_id == company_id)).all()
        return {row.key: row for row in found if _live(row) is not None}


def flag_map(company_id: str) -> dict[str, bool]:
    stored = _rows(company_id)
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
            "created_at": "",
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
        "created_at": live.created_at,
        "updated_at": live.updated_at,
        "deleted_at": live.deleted_at,
    }


def list_features(company_id: str) -> list[dict]:
    stored = _rows(company_id)
    return [_public(company_id, key, stored.get(key)) for key in FEATURE_KEYS]


def export_features() -> list[dict]:
    """Every flag row, including resets, for the stage-1 rollback export."""
    if not _table_ready("company_features"):
        return []
    with store._sql.factory() as session:
        rows = session.scalars(select(CompanyFeature).order_by(CompanyFeature.company_id, CompanyFeature.key)).all()
        return [
            {
                "id": row.id,
                "company_id": row.company_id,
                "key": row.key,
                "enabled": bool(row.enabled),
                "changed_by": row.changed_by,
                "changed_at": row.changed_at,
                "row_version": int(row.row_version),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "deleted_at": row.deleted_at,
            }
            for row in rows
        ]


def _audit(session, company_id: str, key: str, enabled: bool, actor: str, before: bool) -> None:
    audit_write(
        "feature.enable" if enabled else "feature.disable",
        "company_feature",
        key,
        None,
        {"enabled": [before, enabled], "key": key},
        session=session,
        company_id=company_id,
        actor_user_id=actor,
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
    deleted_at = None if enabled else stamp
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
                created_at=stamp,
                updated_at=stamp,
                deleted_at=deleted_at,
            )
            try:
                session.add(row)
                session.flush()
                _audit(session, company_id, key, enabled, actor, False)
                if enabled and key == "punch_photos":
                    from app.punch_photos import import_legacy_for_company

                    import_legacy_for_company(session, company_id)
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise HTTPException(status_code=409, detail="Изменено другим") from exc
            return _public(company_id, key, row)
        tombstone = current.deleted_at is not None
        before = False if tombstone else bool(current.enabled)
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
                deleted_at=deleted_at,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(status_code=409, detail="Изменено другим")
        _audit(session, company_id, key, enabled, actor, before)
        if enabled and key == "punch_photos":
            from app.punch_photos import import_legacy_for_company

            import_legacy_for_company(session, company_id)
        session.commit()
        current.enabled = enabled
        current.changed_by = actor
        current.changed_at = stamp
        current.updated_at = stamp
        current.row_version = new_version
        current.deleted_at = deleted_at
        return _public(company_id, key, current)


def _iso(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        text = value.isoformat(timespec="seconds")
        if text.endswith(("+00:00", "Z")):
            return text.replace("Z", "+00:00")
        if "+" not in text and not text.endswith("Z"):
            return text + "+00:00"
        return text
    return str(value)


def audit_events(company_id: str) -> list[dict]:
    if not _table_ready("audit_log"):
        return []
    with store._sql.factory() as session:
        rows = session.scalars(select(AuditLog).where(AuditLog.company_id == company_id).order_by(AuditLog.id)).all()
        return [
            {
                "id": row.id,
                "action": row.action,
                "company_id": row.company_id,
                "actor_user_id": row.actor_user_id,
                "actor_kind": row.actor_kind,
                "occurred_at": _iso(row.occurred_at),
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "project_id": row.project_id,
                "changes": row.changes,
                "prev_hash": row.prev_hash.hex() if row.prev_hash else None,
                "row_hash": row.row_hash.hex() if row.row_hash else "",
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


def apply_bundle_flags(project, data: dict, flags: dict[str, bool] | None = None) -> dict:
    """Drop feature payloads the company has not turned on. One flag read."""
    company_id = project_company_id(project)
    stored = flags if flags is not None else flag_map(company_id)

    def opened(key: str) -> bool:
        return demo_mode() or bool(stored.get(key))

    if not opened("drawings"):
        data["drawings"] = []
    if not opened("rfi"):
        data["rfis"] = []
    if not opened("submittals"):
        data["submittals"] = []
    if not opened("checklists"):
        data["inspections"] = []
    if not opened("gantt"):
        data["schedule"] = []
    if not opened("meetings"):
        data["meetings"] = []
    if not opened("changes"):
        data["changes"] = []
    if not opened("punch_photos"):
        data["punches"] = [_without_photo(item) for item in data["punches"]]
    data["features"] = stored
    data["company_id"] = company_id
    return data


def ensure_feature(company_id: str, key: str) -> None:
    if not feature_open_for_company(company_id, key):
        raise HTTPException(status_code=404, detail="Не найдено")


def resolve_path_company(collection: str, doc_id: str, user: User) -> str | None:
    """One query for path access. The company id is the owner's stored key, as in the bundle."""
    entity = aliased(Record)
    project = aliased(Record)
    member = aliased(Record)
    project_doc = case((entity.collection == "projects", entity.doc_id), else_=entity.project_id)
    access = or_(
        member.user_id == user.id,
        project.owner_id == user.id,
        project.company_key == company_key(user),
    )
    if user.role == "admin":
        access = true()
    stmt = (
        select(project.owner_id)
        .select_from(entity)
        .join(project, and_(project.collection == "projects", project.doc_id == project_doc))
        .outerjoin(
            member,
            and_(
                member.collection == "directory",
                member.project_id == project.doc_id,
                member.user_id == user.id,
            ),
        )
        .where(entity.collection == collection, entity.doc_id == doc_id, access)
        .limit(1)
    )
    with store._sql.factory() as session:
        found = session.execute(stmt).first()
    if found is None:
        return None
    owner = store.get_user(str(found[0] or ""))
    if owner is None:
        return ""
    return company_key(owner)


def _path_target(path_params) -> tuple[str, str] | None:
    for name, collection in _PATH_IDS:
        value = path_params.get(name)
        if value:
            return collection, str(value)
    return None


def require_feature(key: str):
    """Hide a route when the company flag is off. Ids come from the path, not the query string."""

    if key not in FEATURE_KEYS:
        raise RuntimeError(f"unknown feature {key}")

    def dependency(request: Request, user: User = Depends(require_user)) -> User:
        target = _path_target(request.path_params)
        if target is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        company_id = resolve_path_company(target[0], target[1], user)
        if company_id is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        ensure_feature(company_id, key)
        return user

    return dependency


def assert_bin_or_user(company_id: str) -> None:
    if company_id.startswith("name:") or not (_BIN.match(company_id) or company_id.startswith("user:")):
        raise HTTPException(status_code=404, detail="Не найдено")
