"""Punch items with before/after photos, stored outside the records collection.

Pilot punches stay in the records collection and keep open/ready/closed.
This module reads them once into punch_items (ready→fixed, closed→accepted)
without writing those rows back.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.audit import write as audit_write
from app.pf0_tables import AuditLog
from app.media import strip_image
from app.paths import resolve_stored_file, uploads_dir
from app.schemas import User
from app.store import store

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
_LEGACY = {"ready": "fixed", "closed": "accepted"}
_STATUSES = {"open", "fixed", "accepted", "returned"}
_PROJECT_ROLES = {"owner", "foreman", "supervisor", "procurement", "customer", "supplier", "moderator"}
_FIX_ROLES = {"foreman", "supervisor", "owner"}
_ACCEPT_ROLES = {"supervisor", "owner"}
PUSH_TEXT = "Новое событие по объекту"
_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_MAX_PHOTOS = 8
_ALMATY = ZoneInfo("Asia/Almaty")
_PAGE_W = 1200
_PAGE_H = 842
_LINE_H = 24
_PAGE_MARGIN = 16


class PunchConflict(Exception):
    pass


class PunchForbidden(Exception):
    pass


class PunchBase(DeclarativeBase):
    pass


class PunchItemRow(PunchBase):
    __tablename__ = "punch_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trade: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    assignee_id: Mapped[str | None] = mapped_column(String(80))
    due_date: Mapped[str | None] = mapped_column(String(10))
    author_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    closed_by: Mapped[str | None] = mapped_column(String(80))
    closed_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(80))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))
    legacy_id: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        CheckConstraint("status IN ('open','fixed','accepted','returned')", name="ck_punch_items_status"),
        UniqueConstraint("company_id", "legacy_id", name="uq_punch_items_company_legacy"),
        Index("ix_punch_items_company_updated", "company_id", "updated_at"),
        Index(
            "ix_punch_items_project_status_due",
            "project_id",
            "status",
            "due_date",
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_punch_items_assignee_status",
            "assignee_id",
            "status",
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class PunchPhotoRow(PunchBase):
    __tablename__ = "punch_photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    punch_id: Mapped[str] = mapped_column(String(36), ForeignKey("punch_items.id"), nullable=False)
    phase: Mapped[str] = mapped_column(String(10), nullable=False)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(80))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("phase IN ('before','after')", name="ck_punch_photos_phase"),
        UniqueConstraint("punch_id", "file_id", name="uq_punch_photos_punch_file"),
        Index("ix_punch_photos_file_id", "file_id"),
        Index("ix_punch_photos_company_updated", "company_id", "updated_at"),
        Index(
            "ix_punch_photos_punch_phase",
            "punch_id",
            "phase",
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class FileRow(PunchBase):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(80))
    storage: Mapped[str] = mapped_column(String(10), nullable=False, default="disk")
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    mime: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    meta_stripped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(80))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("storage IN ('disk','s3')", name="ck_files_storage"),
        CheckConstraint("size_bytes >= 0", name="ck_files_size"),
        Index("ix_files_company_updated", "company_id", "updated_at"),
        Index("ix_files_company_sha", "company_id", "sha256"),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(_ALMATY).date().isoformat()


def migrate_status(status: str) -> str:
    mapped = _LEGACY.get(status, status)
    if mapped not in _STATUSES:
        return "open"
    return mapped


def require_uuid(value: str) -> str:
    token = (value or "").strip().lower()
    if not _UUID.match(token):
        raise ValueError("Некорректный идентификатор")
    return token


def legacy_punch_id(project_id: str, punch_id: str) -> str:
    if _UUID.match(punch_id or ""):
        return punch_id.lower()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"anyq:punch:{project_id}:{punch_id}"))


def push_notice(punch_id: str) -> dict:
    return {"text": PUSH_TEXT, "id": punch_id}


def _session() -> Session:
    return store._sql.factory()


def _storage_key(suffix: str) -> str:
    """Server-chosen object name. A client file id is never part of the path."""
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Некорректный файл")
    return f"{uuid.uuid4().hex}{suffix}"


def _write_temp(data: bytes) -> Path:
    folder = uploads_dir() / ".incoming"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.part"
    path.write_bytes(data)
    return path


def _publish_link(temp: Path, storage_key: str) -> None:
    """Hard-link the temp file into place. link fails when dest exists and does not overwrite it."""
    dest = resolve_stored_file("upload", storage_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.link(temp, dest)


def _compensate_unpublished(file_id: str, photo_id: str) -> None:
    """Drop rows that would point at a file the disk publish did not keep."""
    stamp = _now()
    with _session() as session:
        session.execute(
            update(FileRow)
            .where(FileRow.id == file_id, FileRow.deleted_at.is_(None))
            .values(deleted_at=stamp, updated_at=stamp, row_version=FileRow.row_version + 1)
        )
        session.execute(
            update(PunchPhotoRow)
            .where(PunchPhotoRow.id == photo_id, PunchPhotoRow.deleted_at.is_(None))
            .values(deleted_at=stamp, updated_at=stamp, row_version=PunchPhotoRow.row_version + 1)
        )
        session.commit()


def _membership_roles(user_id: str, project_id: str) -> set[str]:
    """Project owner and directory role_on_site. The account role is not consulted."""
    roles: set[str] = set()
    project = store.get_project(project_id)
    if project is not None and project.owner_id == user_id:
        roles.add("owner")
    for row in store.directory.values():
        if row.project_id != project_id or row.user_id != user_id:
            continue
        role = str(row.role_on_site or "").strip().lower()
        if role in _PROJECT_ROLES:
            roles.add(role)
    return roles


def _can_fix(user: User, item: PunchItemRow) -> bool:
    if item.assignee_id and user.id == item.assignee_id:
        return True
    return bool(_membership_roles(user.id, item.project_id) & _FIX_ROLES)


def _can_accept(user: User, item: PunchItemRow) -> bool:
    if user.id == item.author_id:
        return True
    return bool(_membership_roles(user.id, item.project_id) & _ACCEPT_ROLES)


def _can_delete(user: User, item: PunchItemRow) -> bool:
    return "owner" in _membership_roles(user.id, item.project_id)


def _check_transition(user: User, item: PunchItemRow, target: str) -> None:
    if target not in _STATUSES:
        raise PunchConflict()
    current = item.status
    legal_fix = current in {"open", "returned"} and target == "fixed"
    legal_close = current == "fixed" and target in {"accepted", "returned"}
    if not legal_fix and not legal_close:
        raise PunchConflict()
    if legal_fix and not _can_fix(user, item):
        raise PunchForbidden()
    if legal_close and not _can_accept(user, item):
        raise PunchForbidden()


def _photos(session: Session, punch_ids: list[str]) -> dict[str, dict[str, list[str]]]:
    grouped = {punch_id: {"before": [], "after": []} for punch_id in punch_ids}
    if not punch_ids:
        return grouped
    rows = session.scalars(
        select(PunchPhotoRow)
        .where(PunchPhotoRow.punch_id.in_(punch_ids), PunchPhotoRow.deleted_at.is_(None))
        .order_by(PunchPhotoRow.sort_no, PunchPhotoRow.created_at)
    ).all()
    for row in rows:
        bucket = grouped.setdefault(row.punch_id, {"before": [], "after": []})
        if row.phase in bucket:
            bucket[row.phase].append(row.file_id)
    return grouped


def _history_for_project(session: Session, project_id: str, company_id: str, entity_ids: list[str]) -> dict[str, list[dict]]:
    if not entity_ids:
        return {}
    rows = session.scalars(
        select(AuditLog)
        .where(
            AuditLog.action == "punch.status_change",
            AuditLog.project_id == project_id,
            AuditLog.company_id == company_id,
            AuditLog.entity_id.in_(entity_ids),
        )
        .order_by(AuditLog.id)
    ).all()
    found: dict[str, list[dict]] = {}
    for row in rows:
        payload = row.changes if isinstance(row.changes, dict) else {}
        if isinstance(row.changes, str):
            try:
                payload = json.loads(row.changes or "{}")
            except json.JSONDecodeError:
                payload = {}
        moment = row.occurred_at
        stamp = moment.astimezone(UTC).isoformat(timespec="seconds") if hasattr(moment, "astimezone") else str(moment)
        found.setdefault(row.entity_id or "", []).append(
            {
                "at": stamp,
                "actor_id": row.actor_user_id or "",
                "from_status": payload.get("from") if payload.get("from") in _STATUSES else "",
                "to_status": payload.get("to") if payload.get("to") in _STATUSES else "",
            }
        )
    return found


def _overdue(item: PunchItemRow, today: str) -> bool:
    return bool(item.due_date) and item.due_date < today and item.status != "accepted"


def _public(
    item: PunchItemRow,
    photos: dict[str, list[str]],
    history: list[dict],
    user: User,
    today: str,
) -> dict:
    return {
        "id": item.id,
        "company_id": item.company_id,
        "project_id": item.project_id,
        "title": item.title,
        "location": item.location,
        "trade": item.trade,
        "status": item.status,
        "assignee_id": item.assignee_id,
        "due_date": item.due_date,
        "photos_before": photos.get("before", []),
        "photos_after": photos.get("after", []),
        "closed_by": item.closed_by,
        "closed_at": item.closed_at,
        "author_id": item.author_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "row_version": int(item.row_version),
        "deleted_at": item.deleted_at,
        "overdue": _overdue(item, today),
        "history": history,
        "can_fix": item.status in {"open", "returned"} and _can_fix(user, item),
        "can_accept": item.status == "fixed" and _can_accept(user, item),
    }


def _has_after(session: Session, punch_id: str) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(PunchPhotoRow)
        .where(
            PunchPhotoRow.punch_id == punch_id,
            PunchPhotoRow.phase == "after",
            PunchPhotoRow.deleted_at.is_(None),
        )
    )
    return bool(count)


def import_legacy_for_company(session: Session, company_id: str) -> None:
    """Copy pilot punches for one company. Same statement can run again and keeps the latest legacy fields."""
    from app.sql_backend import Record

    projects = session.execute(
        select(Record.doc_id, Record.owner_id).where(Record.collection == "projects", Record.company_key == company_id)
    ).all()
    if not projects:
        return
    owners = {str(row.doc_id): str(row.owner_id or "") for row in projects}
    punches = session.scalars(
        select(Record).where(Record.collection == "punches", Record.project_id.in_(list(owners)))
    ).all()
    if not punches:
        return
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    stamp = _now()
    for row in punches:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if isinstance(row.payload, str):
            try:
                payload = json.loads(row.payload or "{}")
            except json.JSONDecodeError:
                payload = {}
        if not isinstance(payload, dict) or payload.get("deleted_at"):
            continue
        legacy = str(row.doc_id or "").strip()
        project_id = str(row.project_id or payload.get("project_id") or "").strip()
        if not legacy or not project_id or project_id not in owners:
            continue
        owner_id = owners.get(project_id) or ""
        assignee = payload.get("assignee_id")
        assignee_id = str(assignee).strip() if assignee else None
        if assignee_id and (len(assignee_id) > 80 or any(ch.isspace() for ch in assignee_id)):
            assignee_id = None
        values = {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "project_id": project_id,
            "title": str(payload.get("title") or "").strip()[:200] or "item",
            "location": str(payload.get("location") or "")[:200],
            "trade": str(payload.get("trade") or "")[:200],
            "status": migrate_status(str(payload.get("status") or "open")),
            "assignee_id": assignee_id,
            "due_date": None,
            "author_id": owner_id,
            "closed_by": None,
            "closed_at": None,
            "created_at": str(payload.get("created_at") or row.created_at or stamp),
            "created_by": owner_id or None,
            "updated_at": stamp,
            "updated_by": owner_id or None,
            "row_version": 1,
            "deleted_at": None,
            "legacy_id": legacy,
        }
        stmt = insert(PunchItemRow).values(**values)
        excluded = stmt.excluded
        changed = or_(
            PunchItemRow.title.is_distinct_from(excluded.title),
            PunchItemRow.location.is_distinct_from(excluded.location),
            PunchItemRow.trade.is_distinct_from(excluded.trade),
            PunchItemRow.status.is_distinct_from(excluded.status),
            PunchItemRow.assignee_id.is_distinct_from(excluded.assignee_id),
            PunchItemRow.project_id.is_distinct_from(excluded.project_id),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["company_id", "legacy_id"],
            set_={
                "title": excluded.title,
                "location": excluded.location,
                "trade": excluded.trade,
                "status": excluded.status,
                "assignee_id": excluded.assignee_id,
                "project_id": excluded.project_id,
                "updated_at": excluded.updated_at,
                "updated_by": excluded.updated_by,
                "row_version": PunchItemRow.row_version + 1,
            },
            where=changed,
        )
        session.execute(stmt)


def _load(session: Session, punch_id: str, company_id: str, project_id: str) -> PunchItemRow:
    item = session.get(PunchItemRow, punch_id)
    if item is None or item.deleted_at or item.company_id != company_id or item.project_id != project_id:
        raise LookupError()
    return item


def _assignee_or_none(project_id: str, assignee_id: str | None) -> str | None:
    if assignee_id is None or not str(assignee_id).strip():
        return None
    token = str(assignee_id).strip()
    if len(token) > 80 or any(ch.isspace() for ch in token):
        raise ValueError("Некорректный исполнитель")
    person = store.get_user(token)
    project = store.get_project(project_id)
    if person is None or project is None or not store.can_access_project(person, project):
        raise ValueError("Некорректный исполнитель")
    return token


def _due(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    day = str(value).strip()
    if not _DAY.match(day):
        raise ValueError("Некорректная дата")
    return day


def create_item(user: User, project_id: str, company_id: str, body: dict) -> dict:
    punch_id = require_uuid(str(body.get("id") or ""))
    title = str(body.get("title") or "").strip()
    if not title or len(title) > 200:
        raise ValueError("Укажите название")
    location = str(body.get("location") or "").strip()[:200]
    trade = str(body.get("trade") or "").strip()[:200]
    due = _due(body.get("due_date"))
    assignee = _assignee_or_none(project_id, body.get("assignee_id"))
    stamp = _now()
    with _session() as session:
        session.add(
            PunchItemRow(
                id=punch_id,
                company_id=company_id,
                project_id=project_id,
                title=title,
                location=location,
                trade=trade,
                status="open",
                assignee_id=assignee,
                due_date=due,
                author_id=user.id,
                closed_by=None,
                closed_at=None,
                created_at=stamp,
                created_by=user.id,
                updated_at=stamp,
                updated_by=user.id,
                row_version=1,
                deleted_at=None,
            )
        )
        audit_write(
            "punch.create",
            "punch_item",
            punch_id,
            project_id,
            {"status": "open"},
            session=session,
            company_id=company_id,
            actor_user_id=user.id,
        )
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise PunchConflict() from exc
        item = session.get(PunchItemRow, punch_id)
        assert item is not None
        data = _public(item, {"before": [], "after": []}, [], user, _today())
    data["push"] = push_notice(punch_id)
    return data


def list_items(
    user: User,
    project_id: str,
    company_id: str,
    *,
    status: str | None,
    assignee: str | None,
    overdue: bool,
    mine: bool,
) -> list[dict]:
    with _session() as session:
        stmt = select(PunchItemRow).where(
            PunchItemRow.project_id == project_id,
            PunchItemRow.company_id == company_id,
            PunchItemRow.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(PunchItemRow.status == migrate_status(status))
        target = user.id if mine or assignee == "me" else (assignee or None)
        if target:
            stmt = stmt.where(PunchItemRow.assignee_id == target)
        rows = session.scalars(stmt.order_by(PunchItemRow.due_date, PunchItemRow.created_at)).all()
        today = _today()
        if overdue:
            rows = [row for row in rows if _overdue(row, today)]
        ids = [row.id for row in rows]
        photos = _photos(session, ids)
        history = _history_for_project(session, project_id, company_id, ids)
        return [_public(row, photos.get(row.id, {}), history.get(row.id, []), user, today) for row in rows]


def get_item(user: User, punch_id: str, company_id: str, project_id: str) -> dict:
    with _session() as session:
        item = _load(session, punch_id, company_id, project_id)
        photos = _photos(session, [item.id]).get(item.id, {})
        history = _history_for_project(session, item.project_id, company_id, [item.id]).get(item.id, [])
        return _public(item, photos, history, user, _today())


def set_status(user: User, punch_id: str, company_id: str, project_id: str, target: str, row_version: int) -> dict:
    stamp = _now()
    with _session() as session:
        item = _load(session, punch_id, company_id, project_id)
        if int(item.row_version) != int(row_version):
            raise PunchConflict()
        _check_transition(user, item, target)
        if target in {"fixed", "accepted"} and not _has_after(session, punch_id):
            raise PunchConflict()
        previous = item.status
        closed_by = item.closed_by
        closed_at = item.closed_at
        if target == "accepted":
            closed_by = user.id
            closed_at = stamp
        result = session.execute(
            update(PunchItemRow)
            .where(PunchItemRow.id == punch_id, PunchItemRow.row_version == row_version, PunchItemRow.deleted_at.is_(None))
            .values(
                status=target,
                updated_at=stamp,
                updated_by=user.id,
                row_version=row_version + 1,
                closed_by=closed_by,
                closed_at=closed_at,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            raise PunchConflict()
        audit_write(
            "punch.status_change",
            "punch_item",
            punch_id,
            item.project_id,
            {"from": previous, "to": target},
            session=session,
            company_id=company_id,
            actor_user_id=user.id,
        )
        session.commit()
        fresh = session.get(PunchItemRow, punch_id)
        assert fresh is not None
        photos = _photos(session, [punch_id]).get(punch_id, {})
        history = _history_for_project(session, fresh.project_id, company_id, [punch_id]).get(punch_id, [])
        return _public(fresh, photos, history, user, _today())


def _photo_count(session: Session, punch_id: str, phase: str) -> int:
    existing = session.scalar(
        select(func.count())
        .select_from(PunchPhotoRow)
        .where(
            PunchPhotoRow.punch_id == punch_id,
            PunchPhotoRow.phase == phase,
            PunchPhotoRow.deleted_at.is_(None),
        )
    )
    return int(existing or 0)


def add_photo(
    user: User,
    punch_id: str,
    company_id: str,
    project_id: str,
    *,
    photo_id: str,
    client_file_id: str = "",
    phase: str,
    row_version: int,
    raw: bytes,
) -> dict:
    if phase not in {"before", "after"}:
        raise ValueError("Некорректная фаза")
    photo_id = require_uuid(photo_id)
    hint = (client_file_id or "").strip().lower()
    if hint:
        hint = require_uuid(hint)
    with _session() as session:
        item = _load(session, punch_id, company_id, project_id)
        if int(item.row_version) != int(row_version):
            raise PunchConflict()
        if _photo_count(session, punch_id, phase) >= _MAX_PHOTOS:
            raise ValueError("Слишком много фото")
    clean, mime, suffix = strip_image(raw)
    digest = hashlib.sha256(clean).hexdigest()
    with Image.open(io.BytesIO(clean)) as img:
        width, height = img.size
    stamp = _now()
    file_id = str(uuid.uuid4())
    storage_key = _storage_key(suffix)
    if hint and hint in storage_key:
        raise ValueError("Некорректный файл")
    if file_id in storage_key:
        raise ValueError("Некорректный файл")
    temp = _write_temp(clean)
    try:
        with _session() as session:
            item = _load(session, punch_id, company_id, project_id)
            if int(item.row_version) != int(row_version):
                raise PunchConflict()
            sort_no = _photo_count(session, punch_id, phase)
            if sort_no >= _MAX_PHOTOS:
                raise ValueError("Слишком много фото")
            duplicate = session.scalar(
                select(FileRow.id).where(
                    FileRow.company_id == company_id,
                    FileRow.sha256 == digest,
                    FileRow.deleted_at.is_(None),
                )
            )
            result = session.execute(
                update(PunchItemRow)
                .where(PunchItemRow.id == punch_id, PunchItemRow.row_version == row_version, PunchItemRow.deleted_at.is_(None))
                .values(updated_at=stamp, updated_by=user.id, row_version=row_version + 1)
            )
            if result.rowcount != 1:
                session.rollback()
                raise PunchConflict()
            session.add(
                FileRow(
                    id=file_id,
                    company_id=company_id,
                    project_id=item.project_id,
                    storage="disk",
                    storage_key=storage_key,
                    kind="photo_original",
                    mime=mime,
                    size_bytes=len(clean),
                    sha256=digest,
                    width_px=width,
                    height_px=height,
                    meta_stripped=True,
                    created_at=stamp,
                    created_by=user.id,
                    updated_at=stamp,
                    updated_by=user.id,
                    row_version=1,
                    deleted_at=None,
                )
            )
            session.add(
                PunchPhotoRow(
                    id=photo_id,
                    company_id=company_id,
                    project_id=item.project_id,
                    punch_id=punch_id,
                    phase=phase,
                    file_id=file_id,
                    sort_no=sort_no,
                    created_at=stamp,
                    created_by=user.id,
                    updated_at=stamp,
                    updated_by=user.id,
                    row_version=1,
                    deleted_at=None,
                )
            )
            try:
                session.flush()
                audit_write(
                    "punch.photo",
                    "punch_photo",
                    photo_id,
                    item.project_id,
                    {"phase": phase},
                    session=session,
                    company_id=company_id,
                    actor_user_id=user.id,
                )
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise PunchConflict() from exc
            fresh = session.get(PunchItemRow, punch_id)
            assert fresh is not None
            photos = _photos(session, [punch_id]).get(punch_id, {})
            history = _history_for_project(session, fresh.project_id, company_id, [punch_id]).get(punch_id, [])
            payload = _public(fresh, photos, history, user, _today())
        if duplicate:
            payload["warnings"] = ["duplicate_sha256"]
        try:
            _publish_link(temp, storage_key)
        except Exception:
            _compensate_unpublished(file_id, photo_id)
            raise
        return payload
    finally:
        temp.unlink(missing_ok=True)


def file_for_punch(punch_id: str, company_id: str, file_id: str, project_id: str) -> tuple[Path, str]:
    with _session() as session:
        _load(session, punch_id, company_id, project_id)
        row = session.execute(
            select(FileRow)
            .join(PunchPhotoRow, PunchPhotoRow.file_id == FileRow.id)
            .where(
                PunchPhotoRow.punch_id == punch_id,
                PunchPhotoRow.file_id == file_id,
                PunchPhotoRow.company_id == company_id,
                PunchPhotoRow.deleted_at.is_(None),
                FileRow.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError()
        path = resolve_stored_file(row.storage if row.storage != "disk" else "upload", row.storage_key)
        if not path.is_file():
            raise LookupError()
        return path, row.mime


def soft_delete(user: User, punch_id: str, company_id: str, project_id: str, row_version: int) -> dict:
    stamp = _now()
    with _session() as session:
        item = _load(session, punch_id, company_id, project_id)
        if not _can_delete(user, item):
            raise PunchForbidden()
        if int(item.row_version) != int(row_version):
            raise PunchConflict()
        result = session.execute(
            update(PunchItemRow)
            .where(PunchItemRow.id == punch_id, PunchItemRow.row_version == row_version, PunchItemRow.deleted_at.is_(None))
            .values(deleted_at=stamp, updated_at=stamp, updated_by=user.id, row_version=row_version + 1)
        )
        if result.rowcount != 1:
            session.rollback()
            raise PunchConflict()
        audit_write(
            "punch.delete",
            "punch_item",
            punch_id,
            item.project_id,
            {},
            session=session,
            company_id=company_id,
            actor_user_id=user.id,
        )
        session.commit()
        fresh = session.get(PunchItemRow, punch_id)
        assert fresh is not None
        return _public(fresh, {"before": [], "after": []}, [], user, _today())


def redact_pdf_text(value: str) -> str:
    return _PHONE.sub("***", value or "")


def strip_pdf_author(raw: bytes) -> bytes:
    text_value = raw.decode("latin-1")
    text_value = re.sub(r"/Author\s*\([^)]*\)", "", text_value)
    text_value = re.sub(r"/Author\s*<[^>]*>", "", text_value)
    return text_value.encode("latin-1")


def build_pdf(user: User, project_id: str, company_id: str) -> bytes:
    rows = list_items(user, project_id, company_id, status=None, assignee=None, overdue=False, mine=False)
    lines = [f"punches {len(rows)}"]
    for row in rows:
        mark = "overdue" if row["overdue"] else "due"
        lines.append(
            " | ".join(
                [
                    row["id"],
                    row["status"],
                    row["due_date"] or "-",
                    mark,
                    redact_pdf_text(row["location"]),
                    redact_pdf_text(row["title"]),
                ]
            )
        )
    font = ImageFont.truetype(str(_FONT), 16) if _FONT.is_file() else ImageFont.load_default()
    per_page = max(1, (_PAGE_H - 2 * _PAGE_MARGIN) // _LINE_H)
    chunks = [lines[index : index + per_page] for index in range(0, len(lines), per_page)] or [[]]
    pages: list[Image.Image] = []
    for chunk in chunks:
        image = Image.new("RGB", (_PAGE_W, _PAGE_H), "white")
        draw = ImageDraw.Draw(image)
        y = _PAGE_MARGIN
        for line in chunk:
            draw.text((12, y), line[:180], fill="black", font=font)
            y += _LINE_H
        pages.append(image)
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return strip_pdf_author(buffer.getvalue())
