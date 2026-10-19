"""Drawing sheets stored in their own tables, with compare-and-swap writes."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import and_, or_, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.audit import write as audit_write
from app.company_features import ensure_feature
from app.drawing_models import DrawingRevisionRow, DrawingRow, DrawingSetRow, StoredFile
from app.paths import discard_upload, publish_upload, resolve_stored_file, stage_upload
from app.pdf_clean import strip_pdf
from app.schemas import User
from app.sql_backend import Record
from app.store import store
from app.tenant import company_key

MAX_PDF_BYTES = 50 * 1024 * 1024
UPLOAD_ROLES = frozenset({"owner", "supervisor"})
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class DrawingConflict(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def _allowed(project, member, user: User):
    """Same membership rule as resolve_path_company: owner, directory, or stored company key."""
    access = or_(
        member.user_id == user.id,
        project.owner_id == user.id,
        project.company_key == company_key(user),
    )
    if user.role == "admin":
        return true()
    return access


def _access_columns(project, member):
    return (
        project.doc_id.label("project_id"),
        project.owner_id.label("owner_id"),
        member.payload["role_on_site"].as_string().label("site_role"),
    )


def _with_membership(stmt, project, user: User):
    member = aliased(Record)
    return (
        stmt.add_columns(*_access_columns(project, member))
        .outerjoin(
            member,
            and_(
                member.collection == "directory",
                member.project_id == project.doc_id,
                member.user_id == user.id,
            ),
        )
        .where(_allowed(project, member, user))
        .limit(1)
    )


def _access_statement(kind: str, path_id: str, user: User):
    project = aliased(Record)
    if kind == "project":
        return _with_membership(
            select()
            .select_from(project)
            .where(project.collection == "projects", project.doc_id == path_id),
            project,
            user,
        )
    return _with_membership(
        select()
        .select_from(DrawingRow)
        .join(project, and_(project.collection == "projects", project.doc_id == DrawingRow.project_id))
        .where(DrawingRow.id == path_id, DrawingRow.deleted_at.is_(None)),
        project,
        user,
    )


def path_entity(request: Request) -> tuple[str, str]:
    """Ids come from the path only. A query pid or did cannot select another row."""
    params = request.path_params
    if "did" in params and str(params["did"]).strip():
        return "drawing", str(params["did"]).strip()
    if "pid" in params and str(params["pid"]).strip():
        return "project", str(params["pid"]).strip()
    raise HTTPException(status_code=404, detail="Не найдено")


def load_access(request: Request, user: User) -> Access:
    kind, path_id = path_entity(request)
    with store._sql.factory() as session:
        row = session.execute(_access_statement(kind, path_id, user)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    owner = store.get_user(str(row.owner_id or ""))
    company_id = company_key(owner) if owner is not None else ""
    if not company_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    ensure_feature(company_id, "drawings")
    return Access(
        company_id=company_id,
        project_id=str(row.project_id),
        user_id=user.id,
        user_role=_clean(user.role),
        site_role=_clean(row.site_role),
        is_owner=str(row.owner_id or "") == user.id,
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


def _prepare_pdf(raw: bytes) -> tuple[bytes, str, Path]:
    cleaned = _read_pdf(raw)
    key, tmp = stage_upload("drawing_pdf", cleaned)
    return cleaned, key, tmp


def _store_file(session, access: Access, file_id: str, cleaned: bytes, storage_key: str, stamp: str, user_id: str) -> None:
    session.add(
        StoredFile(
            id=file_id,
            company_id=access.company_id,
            project_id=access.project_id,
            storage_key=storage_key,
            kind="drawing_pdf",
            mime="application/pdf",
            size_bytes=len(cleaned),
            sha256=hashlib.sha256(cleaned).hexdigest(),
            meta_stripped=True,
            created_by=user_id,
            updated_by=user_id,
            created_at=stamp,
            updated_at=stamp,
            row_version=1,
            deleted_at=None,
        )
    )


def _use_set(
    session,
    access: Access,
    *,
    set_id: str | None,
    set_title: str | None,
    discipline: str | None,
    stamp: str,
    label: str,
    user_id: str,
) -> DrawingSetRow | None:
    if set_id:
        existing = session.get(DrawingSetRow, set_id)
        if existing is not None:
            if existing.deleted_at or existing.project_id != access.project_id:
                raise HTTPException(status_code=404, detail="Не найдено")
            return existing
    elif not (set_title or "").strip():
        return None
    row = DrawingSetRow(
        id=set_id or str(uuid4()),
        company_id=access.company_id,
        project_id=access.project_id,
        title=_clip(set_title, 120, label),
        discipline=_clip(discipline, 40),
        created_by=user_id,
        updated_by=user_id,
        created_at=stamp,
        updated_at=stamp,
        row_version=1,
        deleted_at=None,
    )
    session.add(row)
    session.flush()
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
    cleaned, storage_key, staged = _prepare_pdf(raw)
    stamp = _now()
    label = _clip(title, 120, "sheet")
    chosen_code = _clip(code, 32).upper() or _code_from(label, drawing_id)
    chosen_rev = _clip(rev, 16).upper() or "A"
    committed = False
    try:
        with store._sql.factory() as session:
            try:
                sheet_set = _use_set(
                    session,
                    access,
                    set_id=set_id,
                    set_title=set_title,
                    discipline=discipline,
                    stamp=stamp,
                    label=label,
                    user_id=user_id,
                )
                drawing = DrawingRow(
                    id=drawing_id,
                    company_id=access.company_id,
                    project_id=access.project_id,
                    set_id=sheet_set.id if sheet_set else None,
                    code=chosen_code,
                    title=label,
                    created_by=user_id,
                    updated_by=user_id,
                    created_at=stamp,
                    updated_at=stamp,
                    row_version=1,
                    deleted_at=None,
                )
                session.add(drawing)
                session.flush()
                _store_file(session, access, file_id, cleaned, storage_key, stamp, user_id)
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
                    actor_user_id=user_id,
                )
                session.commit()
                committed = True
                result = _sheet_out(drawing, _revisions_for(session, drawing_id), sheet_set)
            except IntegrityError as exc:
                session.rollback()
                _conflict(exc)
    finally:
        if committed:
            publish_upload("drawing_pdf", storage_key, staged)
        else:
            discard_upload(staged)
    return result


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
    cleaned, storage_key, staged = _prepare_pdf(raw)
    stamp = _now()
    committed = False
    try:
        with store._sql.factory() as session:
            try:
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
                bumped = session.execute(
                    update(DrawingRow)
                    .where(
                        DrawingRow.id == drawing_id,
                        DrawingRow.row_version == row_version,
                        DrawingRow.deleted_at.is_(None),
                    )
                    .values(row_version=row_version + 1, updated_at=stamp, updated_by=user_id)
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
                _store_file(session, access, file_id, cleaned, storage_key, stamp, user_id)
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
                    actor_user_id=user_id,
                )
                session.commit()
                committed = True
                session.refresh(drawing)
                sheet_set = session.get(DrawingSetRow, drawing.set_id) if drawing.set_id else None
                result = _sheet_out(drawing, _revisions_for(session, drawing_id), sheet_set)
            except IntegrityError as exc:
                session.rollback()
                _conflict(exc)
    finally:
        if committed:
            publish_upload("drawing_pdf", storage_key, staged)
        else:
            discard_upload(staged)
    return result


def _project_sheets(session, project_id: str) -> list[dict]:
    current = aliased(DrawingRevisionRow)
    rows = session.execute(
        select(DrawingRow, DrawingSetRow, current)
        .outerjoin(
            current,
            and_(
                current.drawing_id == DrawingRow.id,
                current.is_current.is_(True),
                current.deleted_at.is_(None),
            ),
        )
        .outerjoin(DrawingSetRow, and_(DrawingSetRow.id == DrawingRow.set_id, DrawingSetRow.deleted_at.is_(None)))
        .where(DrawingRow.project_id == project_id, DrawingRow.deleted_at.is_(None))
        .order_by(DrawingRow.created_at, DrawingRow.code)
    ).all()
    grouped: dict[str, list[DrawingRevisionRow]] = defaultdict(list)
    for item in session.scalars(
        select(DrawingRevisionRow)
        .where(DrawingRevisionRow.project_id == project_id, DrawingRevisionRow.deleted_at.is_(None))
        .order_by(DrawingRevisionRow.uploaded_at, DrawingRevisionRow.rev)
    ).all():
        grouped[item.drawing_id].append(item)
    sheets = []
    for drawing, sheet_set, current_row in rows:
        revisions = grouped.get(drawing.id) or ([current_row] if current_row is not None else [])
        sheets.append(_sheet_out(drawing, revisions, sheet_set))
    return sheets


def sheets_for_project(project_id: str) -> list[dict]:
    with store._sql.factory() as session:
        return _project_sheets(session, project_id)


def list_sheets(access: Access) -> dict:
    with store._sql.factory() as session:
        sheets = _project_sheets(session, access.project_id)
    return {"can_upload": access.can_upload, "sheets": sheets}


def get_sheet(access: Access, drawing_id: str, rev: str | None) -> dict:
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
