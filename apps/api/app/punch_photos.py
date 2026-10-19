"""Punch items with before/after photos, stored outside the records collection.

Pilot punches stay in the records collection and keep open/ready/closed.
This module reads them once into punch_items (ready→fixed, closed→accepted)
without writing those rows back.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.audit import write as audit_write
from app.pf0_tables import AuditLog
from app.media import strip_image
from app.paths import resolve_stored_file, write_stored_file
from app.schemas import User
from app.store import store

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
_LEGACY = {"ready": "fixed", "closed": "accepted"}
_STATUSES = {"open", "fixed", "accepted", "returned"}
_TRANSITIONS = {
    ("member", "open", "fixed"),
    ("member", "returned", "fixed"),
    ("author", "fixed", "accepted"),
    ("supervisor", "fixed", "accepted"),
    ("author", "fixed", "returned"),
    ("supervisor", "fixed", "returned"),
}
PUSH_TEXT = "Новое событие по объекту"
_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_MAX_PHOTOS = 8


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
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("status IN ('open','fixed','accepted','returned')", name="ck_punch_items_status"),
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
    punch_id: Mapped[str] = mapped_column(String(36), nullable=False)
    phase: Mapped[str] = mapped_column(String(10), nullable=False)
    file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("phase IN ('before','after')", name="ck_punch_photos_phase"),
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
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("storage IN ('disk','s3')", name="ck_files_storage"),
        CheckConstraint("size_bytes >= 0", name="ck_files_size"),
        Index("ix_files_company_updated", "company_id", "updated_at"),
        Index("ix_files_company_sha", "company_id", "sha256"),
    )


_schema_ready = False


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    PunchBase.metadata.create_all(store._sql.engine)
    _schema_ready = True


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


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
    ensure_schema()
    return store._sql.factory()


def _actors(user: User, author_id: str, project_id: str) -> set[str]:
    roles = {"member"}
    if user.id == author_id:
        roles.add("author")
    if user.role == "supervisor" or _directory_supervisor(user.id, project_id):
        roles.add("supervisor")
    return roles


def _directory_supervisor(user_id: str, project_id: str) -> bool:
    for row in store.directory.values():
        if row.project_id == project_id and row.user_id == user_id and row.role_on_site == "supervisor":
            return True
    return False


def _check_transition(user: User, item: PunchItemRow, target: str) -> None:
    if target not in _STATUSES:
        raise PunchConflict()
    current = item.status
    roles = _actors(user, item.author_id, item.project_id)
    allowed = any((role, current, target) in _TRANSITIONS for role in roles)
    exists = any(src == current and dst == target for _role, src, dst in _TRANSITIONS)
    if not allowed and exists:
        raise PunchForbidden()
    if not allowed:
        raise PunchConflict()


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


def _history_for_project(session: Session, project_id: str) -> dict[str, list[dict]]:
    rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.action == "punch.status_change", AuditLog.project_id == project_id)
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
        "can_fix": item.status in {"open", "returned"},
        "can_accept": item.status == "fixed" and bool(_actors(user, item.author_id, item.project_id) & {"author", "supervisor"}),
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


def _import_legacy(session: Session, project_id: str, company_id: str) -> None:
    project = store.get_project(project_id)
    if project is None:
        return
    stamp = _now()
    for item in list(store.punches.values()):
        if getattr(item, "project_id", "") != project_id:
            continue
        if getattr(item, "deleted_at", None):
            continue
        new_id = legacy_punch_id(project_id, item.id)
        if session.get(PunchItemRow, new_id) is not None:
            continue
        session.add(
            PunchItemRow(
                id=new_id,
                company_id=company_id,
                project_id=project_id,
                title=str(item.title or "").strip() or "item",
                location=str(getattr(item, "location", "") or ""),
                trade=str(getattr(item, "trade", "") or ""),
                status=migrate_status(str(item.status or "open")),
                assignee_id=getattr(item, "assignee_id", None) or None,
                due_date=None,
                author_id=project.owner_id or "",
                closed_by=None,
                closed_at=None,
                created_at=getattr(item, "created_at", "") or stamp,
                updated_at=stamp,
                row_version=1,
                deleted_at=None,
            )
        )
    session.commit()


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
                updated_at=stamp,
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
        _import_legacy(session, project_id, company_id)
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
        history = _history_for_project(session, project_id)
        return [_public(row, photos.get(row.id, {}), history.get(row.id, []), user, today) for row in rows]


def get_item(user: User, punch_id: str, company_id: str, project_id: str) -> dict:
    with _session() as session:
        item = _load(session, punch_id, company_id, project_id)
        photos = _photos(session, [item.id]).get(item.id, {})
        history = _history_for_project(session, item.project_id).get(item.id, [])
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
        history = _history_for_project(session, fresh.project_id).get(punch_id, [])
        return _public(fresh, photos, history, user, _today())


def add_photo(
    user: User,
    punch_id: str,
    company_id: str,
    project_id: str,
    *,
    photo_id: str,
    file_id: str,
    phase: str,
    row_version: int,
    raw: bytes,
) -> dict:
    if phase not in {"before", "after"}:
        raise ValueError("Некорректная фаза")
    photo_id = require_uuid(photo_id)
    file_id = require_uuid(file_id)
    clean, mime, suffix = strip_image(raw)
    digest = hashlib.sha256(clean).hexdigest()
    with Image.open(io.BytesIO(clean)) as img:
        width, height = img.size
    stamp = _now()
    with _session() as session:
        item = _load(session, punch_id, company_id, project_id)
        if int(item.row_version) != int(row_version):
            raise PunchConflict()
        existing = session.scalar(
            select(func.count())
            .select_from(PunchPhotoRow)
            .where(
                PunchPhotoRow.punch_id == punch_id,
                PunchPhotoRow.phase == phase,
                PunchPhotoRow.deleted_at.is_(None),
            )
        )
        if int(existing or 0) >= _MAX_PHOTOS:
            raise ValueError("Слишком много фото")
        sort_no = int(existing or 0)
        storage_key = f"{item.project_id}/punch/{file_id}{suffix}"
        written = write_stored_file("upload", storage_key, clean)
        result = session.execute(
            update(PunchItemRow)
            .where(PunchItemRow.id == punch_id, PunchItemRow.row_version == row_version, PunchItemRow.deleted_at.is_(None))
            .values(updated_at=stamp, row_version=row_version + 1)
        )
        if result.rowcount != 1:
            session.rollback()
            written.unlink(missing_ok=True)
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
                updated_at=stamp,
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
                updated_at=stamp,
                row_version=1,
                deleted_at=None,
            )
        )
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
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            written.unlink(missing_ok=True)
            raise PunchConflict() from exc
        fresh = session.get(PunchItemRow, punch_id)
        assert fresh is not None
        photos = _photos(session, [punch_id]).get(punch_id, {})
        history = _history_for_project(session, fresh.project_id).get(punch_id, [])
        return _public(fresh, photos, history, user, _today())


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
        roles = _actors(user, item.author_id, item.project_id)
        if not roles & {"author", "supervisor"}:
            raise PunchForbidden()
        if int(item.row_version) != int(row_version):
            raise PunchConflict()
        result = session.execute(
            update(PunchItemRow)
            .where(PunchItemRow.id == punch_id, PunchItemRow.row_version == row_version, PunchItemRow.deleted_at.is_(None))
            .values(deleted_at=stamp, updated_at=stamp, row_version=row_version + 1)
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
    line_h = 24
    image = Image.new("RGB", (1200, 32 + line_h * max(1, len(lines))), "white")
    draw = ImageDraw.Draw(image)
    y = 12
    for line in lines:
        draw.text((12, y), line[:220], fill="black", font=font)
        y += line_h
    buffer = io.BytesIO()
    image.save(buffer, format="PDF")
    return strip_pdf_author(buffer.getvalue())
