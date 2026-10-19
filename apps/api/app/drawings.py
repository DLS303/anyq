"""Drawing sheets stored in their own tables, with compare-and-swap writes."""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlalchemy import and_, exists, inspect, or_, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import aliased

from types import SimpleNamespace

from app.audit import write as audit_write
from app.company_features import company_id_of, ensure_feature
from app.drawing_models import DrawingRevisionRow, DrawingRow, DrawingSetRow, StoredFile
from app.paths import resolve_stored_file, write_stored_file
from app.pdf_clean import strip_pdf
from app.sql_backend import Base, Record
from app.store import store

MAX_PDF_BYTES = 50 * 1024 * 1024
UPLOAD_ROLES = frozenset({"owner", "supervisor"})
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_AUDIT_COLUMNS = (
    ("entity_type", "VARCHAR(64)"),
    ("entity_id", "VARCHAR(36)"),
    ("project_id", "VARCHAR(80)"),
    ("changes", "TEXT"),
)
_ready = False
_lock = threading.Lock()


class DrawingConflict(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def ensure_schema() -> None:
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        Base.metadata.create_all(
            store._sql.engine,
            tables=[
                StoredFile.__table__,
                DrawingSetRow.__table__,
                DrawingRow.__table__,
                DrawingRevisionRow.__table__,
            ],
        )
        _ensure_audit_columns()
        _ready = True


def _ensure_audit_columns() -> None:
    binder = store._sql.engine
    if not inspect(binder).has_table("audit_log"):
        return
    have = {col["name"] for col in inspect(binder).get_columns("audit_log")}
    missing = [(name, ddl) for name, ddl in _AUDIT_COLUMNS if name not in have]
    if not missing:
        return
    with binder.begin() as conn:
        for name, ddl in missing:
            try:
                conn.execute(text(f"ALTER TABLE audit_log ADD COLUMN {name} {ddl}"))
            except OperationalError:
                continue


def parse_uuid(value: str | None, *, required: bool = True) -> str | None:
    token = (value or "").strip()
    if not token:
        if required:
            raise HTTPException(status_code=400, detail="Некорректный идентификатор")
        return None
    if not _UUID.match(token):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    return token.lower()


@dataclass(frozen=True)
class Access:
    company_id: str
    project_id: str
    user_id: str
    user_role: str
    site_role: str
    is_owner: bool

    @property
    def can_upload(self) -> bool:
        if self.is_owner:
            return True
        return self.user_role in UPLOAD_ROLES or self.site_role in UPLOAD_ROLES


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().strip('"')


def _access_statement(kind: str, path_id: str, user_id: str):
    project = aliased(Record)
    member = aliased(Record)
    owner = aliased(Record)
    seat = aliased(Record)
    listed = aliased(Record)
    site_role = (
        select(seat.payload["role_on_site"].as_string())
        .where(
            seat.collection == "directory",
            seat.project_id == project.doc_id,
            seat.user_id == user_id,
        )
        .limit(1)
        .scalar_subquery()
    )
    columns = (
        project.doc_id.label("project_id"),
        owner.doc_id.label("owner_id"),
        owner.payload["company_bin"].as_string().label("owner_bin"),
        owner.company_key.label("company_key"),
        member.payload["role"].as_string().label("user_role"),
        site_role.label("site_role"),
        (member.doc_id == project.owner_id).label("is_owner"),
    )
    member_ok = or_(
        member.doc_id == project.owner_id,
        and_(member.company_key == owner.company_key, owner.company_key.like("bin:%")),
        exists(
            select(listed.doc_id).where(
                listed.collection == "directory",
                listed.project_id == project.doc_id,
                listed.user_id == user_id,
            )
        ),
    )
    if kind == "project":
        entity = aliased(Record)
        return (
            select(*columns)
            .select_from(entity)
            .join(project, and_(project.collection == "projects", project.doc_id == entity.doc_id))
            .join(owner, and_(owner.collection == "users", owner.doc_id == project.owner_id))
            .join(member, and_(member.collection == "users", member.doc_id == user_id))
            .where(entity.collection == "projects", entity.doc_id == path_id, member_ok)
        )
    return (
        select(*columns)
        .select_from(DrawingRow)
        .join(project, and_(project.collection == "projects", project.doc_id == DrawingRow.project_id))
        .join(owner, and_(owner.collection == "users", owner.doc_id == project.owner_id))
        .join(member, and_(member.collection == "users", member.doc_id == user_id))
        .where(DrawingRow.id == path_id, DrawingRow.deleted_at.is_(None), member_ok)
    )


def path_entity(request: Request) -> tuple[str, str]:
    """Ids come from the path only. A query pid or did cannot select another row."""
    params = request.path_params
    if "did" in params and str(params["did"]).strip():
        return "drawing", str(params["did"]).strip()
    if "pid" in params and str(params["pid"]).strip():
        return "project", str(params["pid"]).strip()
    raise HTTPException(status_code=404, detail="Не найдено")


def load_access(request: Request, user_id: str) -> Access:
    ensure_schema()
    kind, path_id = path_entity(request)
    with store._sql.factory() as session:
        row = session.execute(_access_statement(kind, path_id, user_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    company_id = company_id_of(SimpleNamespace(id=str(row.owner_id), company_bin=_clean(row.owner_bin)))
    ensure_feature(company_id, "drawings")
    return Access(
        company_id=company_id,
        project_id=str(row.project_id),
        user_id=user_id,
        user_role=_clean(row.user_role),
        site_role=_clean(row.site_role),
        is_owner=bool(row.is_owner),
    )


def _clip(value: str | None, limit: int, fallback: str = "") -> str:
    token = " ".join((value or "").split())
    if not token:
        return fallback
    return token[:limit]


def _code_from(title: str, drawing_id: str) -> str:
    raw = "".join(ch for ch in title.upper() if ch.isalnum())[:16]
    return raw or drawing_id.replace("-", "")[:8].upper()


def _next_rev(taken: set[str]) -> str:
    if not taken:
        return "A"
    letters = [item for item in taken if len(item) == 1 and item.isalpha()]
    if letters and len(letters) == len(taken):
        last = max(letters)
        if last < "Z":
            return chr(ord(last) + 1)
    number = 1
    while str(number) in taken:
        number += 1
    return str(number)


def _rev_out(row: DrawingRevisionRow) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "drawing_id": row.drawing_id,
        "rev": row.rev,
        "file_id": row.file_id,
        "is_current": bool(row.is_current),
        "uploaded_by": row.uploaded_by,
        "uploaded_at": row.uploaded_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "row_version": int(row.row_version),
        "deleted_at": row.deleted_at,
    }


def _sheet_out(drawing: DrawingRow, revisions: list[DrawingRevisionRow], sheet_set: DrawingSetRow | None) -> dict:
    current = next((item for item in revisions if item.is_current), None)
    return {
        "id": drawing.id,
        "company_id": drawing.company_id,
        "project_id": drawing.project_id,
        "set_id": drawing.set_id,
        "set_title": sheet_set.title if sheet_set else "",
        "discipline": sheet_set.discipline if sheet_set else "",
        "code": drawing.code,
        "title": drawing.title,
        "created_at": drawing.created_at,
        "updated_at": drawing.updated_at,
        "row_version": int(drawing.row_version),
        "deleted_at": drawing.deleted_at,
        "current_rev": current.rev if current else "",
        "revisions": [_rev_out(item) for item in revisions],
    }


def _revisions_for(session, drawing_id: str) -> list[DrawingRevisionRow]:
    rows = session.scalars(
        select(DrawingRevisionRow)
        .where(DrawingRevisionRow.drawing_id == drawing_id, DrawingRevisionRow.deleted_at.is_(None))
        .order_by(DrawingRevisionRow.uploaded_at, DrawingRevisionRow.rev)
    ).all()
    return list(rows)


def _read_pdf(raw: bytes) -> bytes:
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше лимита")
    try:
        return strip_pdf(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Только PDF") from exc


def _store_file(session, access: Access, file_id: str, raw: bytes, stamp: str) -> StoredFile:
    cleaned = _read_pdf(raw)
    digest = hashlib.sha256(cleaned).hexdigest()
    storage_key = f"{file_id}.pdf"
    write_stored_file("drawing_pdf", storage_key, cleaned)
    row = StoredFile(
        id=file_id,
        company_id=access.company_id,
        project_id=access.project_id,
        storage_key=storage_key,
        kind="drawing_pdf",
        mime="application/pdf",
        size_bytes=len(cleaned),
        sha256=digest,
        meta_stripped=True,
        created_at=stamp,
        updated_at=stamp,
        row_version=1,
        deleted_at=None,
    )
    session.add(row)
    return row


def _conflict(exc: IntegrityError) -> None:
    raise DrawingConflict(str(exc.orig)) from exc


def create_sheet(
    access: Access,
    *,
    user_id: str,
    drawing_id: str,
    revision_id: str,
    file_id: str,
    raw: bytes,
    title: str | None,
    code: str | None,
    rev: str | None,
    set_id: str | None,
    set_title: str | None,
    discipline: str | None,
    row_version: int | None,
) -> dict:
    if not access.can_upload:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    if row_version not in (None, 0):
        raise DrawingConflict()
    ensure_schema()
    stamp = _now()
    label = _clip(title, 120, "sheet")
    chosen_code = _clip(code, 32).upper() or _code_from(label, drawing_id)
    chosen_rev = _clip(rev, 16).upper() or "A"
    with store._sql.factory() as session:
        try:
            sheet_set = None
            if set_id or (set_title or "").strip():
                set_key = set_id or drawing_id
                sheet_set = DrawingSetRow(
                    id=set_key,
                    company_id=access.company_id,
                    project_id=access.project_id,
                    title=_clip(set_title, 120, label),
                    discipline=_clip(discipline, 40),
                    created_at=stamp,
                    updated_at=stamp,
                    row_version=1,
                    deleted_at=None,
                )
                session.add(sheet_set)
                session.flush()
            drawing = DrawingRow(
                id=drawing_id,
                company_id=access.company_id,
                project_id=access.project_id,
                set_id=sheet_set.id if sheet_set else None,
                code=chosen_code,
                title=label,
                created_at=stamp,
                updated_at=stamp,
                row_version=1,
                deleted_at=None,
            )
            session.add(drawing)
            session.flush()
            _store_file(session, access, file_id, raw, stamp)
            session.flush()
            session.add(
                DrawingRevisionRow(
                    id=revision_id,
                    company_id=access.company_id,
                    project_id=access.project_id,
                    drawing_id=drawing_id,
                    rev=chosen_rev,
                    file_id=file_id,
                    is_current=True,
                    uploaded_by=user_id,
                    uploaded_at=stamp,
                    created_at=stamp,
                    updated_at=stamp,
                    row_version=1,
                    deleted_at=None,
                )
            )
            audit_write(
                "drawing.upload",
                "drawing_revision",
                revision_id,
                access.project_id,
                {"rev": chosen_rev, "file_id": file_id, "drawing_id": drawing_id},
                session=session,
                company_id=access.company_id,
                actor=user_id,
            )
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            _conflict(exc)
        revisions = _revisions_for(session, drawing_id)
        return _sheet_out(drawing, revisions, sheet_set)


def add_revision(
    access: Access,
    drawing_id: str,
    *,
    user_id: str,
    revision_id: str,
    file_id: str,
    raw: bytes,
    rev: str | None,
    row_version: int | None,
) -> dict:
    if not access.can_upload:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    if row_version is None:
        raise HTTPException(status_code=400, detail="Некорректная версия")
    ensure_schema()
    stamp = _now()
    with store._sql.factory() as session:
        drawing = session.get(DrawingRow, drawing_id)
        if drawing is None or drawing.deleted_at or drawing.project_id != access.project_id:
            raise HTTPException(status_code=404, detail="Не найдено")
        taken = {
            item.rev
            for item in session.scalars(
                select(DrawingRevisionRow).where(
                    DrawingRevisionRow.drawing_id == drawing_id,
                    DrawingRevisionRow.deleted_at.is_(None),
                )
            ).all()
        }
        chosen = _clip(rev, 16).upper() or _next_rev(taken)
        if chosen in taken:
            raise DrawingConflict()
        try:
            bumped = session.execute(
                update(DrawingRow)
                .where(
                    DrawingRow.id == drawing_id,
                    DrawingRow.row_version == row_version,
                    DrawingRow.deleted_at.is_(None),
                )
                .values(row_version=row_version + 1, updated_at=stamp)
            )
            if bumped.rowcount != 1:
                session.rollback()
                raise DrawingConflict()
            session.execute(
                update(DrawingRevisionRow)
                .where(
                    DrawingRevisionRow.drawing_id == drawing_id,
                    DrawingRevisionRow.is_current.is_(True),
                    DrawingRevisionRow.deleted_at.is_(None),
                )
                .values(is_current=False, row_version=DrawingRevisionRow.row_version + 1, updated_at=stamp)
            )
            _store_file(session, access, file_id, raw, stamp)
            session.flush()
            session.add(
                DrawingRevisionRow(
                    id=revision_id,
                    company_id=drawing.company_id,
                    project_id=drawing.project_id,
                    drawing_id=drawing_id,
                    rev=chosen,
                    file_id=file_id,
                    is_current=True,
                    uploaded_by=user_id,
                    uploaded_at=stamp,
                    created_at=stamp,
                    updated_at=stamp,
                    row_version=1,
                    deleted_at=None,
                )
            )
            audit_write(
                "drawing.upload",
                "drawing_revision",
                revision_id,
                drawing.project_id,
                {"rev": chosen, "file_id": file_id, "drawing_id": drawing_id},
                session=session,
                company_id=drawing.company_id,
                actor=user_id,
            )
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            _conflict(exc)
        session.refresh(drawing)
        sheet_set = session.get(DrawingSetRow, drawing.set_id) if drawing.set_id else None
        return _sheet_out(drawing, _revisions_for(session, drawing_id), sheet_set)


def list_sheets(access: Access) -> dict:
    ensure_schema()
    with store._sql.factory() as session:
        drawings = session.scalars(
            select(DrawingRow)
            .where(DrawingRow.project_id == access.project_id, DrawingRow.deleted_at.is_(None))
            .order_by(DrawingRow.created_at, DrawingRow.code)
        ).all()
        sets = {
            item.id: item
            for item in session.scalars(
                select(DrawingSetRow).where(
                    DrawingSetRow.project_id == access.project_id,
                    DrawingSetRow.deleted_at.is_(None),
                )
            ).all()
        }
        sheets = []
        for drawing in drawings:
            sheets.append(_sheet_out(drawing, _revisions_for(session, drawing.id), sets.get(drawing.set_id or "")))
    return {"can_upload": access.can_upload, "sheets": sheets}


def get_sheet(access: Access, drawing_id: str, rev: str | None) -> dict:
    ensure_schema()
    with store._sql.factory() as session:
        drawing = session.get(DrawingRow, drawing_id)
        if drawing is None or drawing.deleted_at or drawing.project_id != access.project_id:
            raise HTTPException(status_code=404, detail="Не найдено")
        revisions = _revisions_for(session, drawing_id)
        sheet_set = session.get(DrawingSetRow, drawing.set_id) if drawing.set_id else None
        body = _sheet_out(drawing, revisions, sheet_set)
    wanted = (rev or "").strip()
    selected = None
    if wanted:
        selected = next((item for item in body["revisions"] if item["rev"] == wanted), None)
        if selected is None:
            raise HTTPException(status_code=404, detail="Не найдено")
    else:
        selected = next((item for item in body["revisions"] if item["is_current"]), None)
    body["selected"] = selected
    body["newer"] = bool(selected and body["current_rev"] and selected["rev"] != body["current_rev"])
    body["can_upload"] = access.can_upload
    return body


def open_file(access: Access, drawing_id: str, rev: str | None):
    sheet = get_sheet(access, drawing_id, rev)
    selected = sheet.get("selected")
    if not selected:
        raise HTTPException(status_code=404, detail="Не найдено")
    with store._sql.factory() as session:
        stored = session.get(StoredFile, selected["file_id"])
    if stored is None or stored.deleted_at or stored.project_id != access.project_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    try:
        path = resolve_stored_file(stored.kind, stored.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Не найдено") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Не найдено")
    return path
