"""Markups on a drawing revision. Writes are compare-and-set in one transaction."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.audit import write as audit_write
from app.company_features import ensure_feature
from app.drawing_models import DrawingRevisionRow, DrawingRow, StoredFile
from app.markup_models import MarkupRow
from app.media import MAX_UPLOAD_BYTES, strip_image
from app.paths import discard_upload, publish_upload, resolve_stored_file, stage_upload
from app.schemas import User
from app.sql_backend import Record
from app.store import store
from app.tenant import company_key

PHOTO_KIND = "markup_photo"
_DOWNLOAD_NAMES = {
    "image/jpeg": "photo.jpg",
    "image/png": "photo.png",
    "image/webp": "photo.webp",
}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_TOOLS = frozenset({"arrow", "cloud", "text", "photo"})
_READ_ONLY = frozenset({"customer"})


class MarkupConflict(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_uuid(value: object, *, required: bool = True) -> str | None:
    token = str(value or "").strip()
    if not token:
        if required:
            raise HTTPException(status_code=400, detail="Некорректный идентификатор")
        return None
    if not _UUID.match(token):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    return token.lower()


@dataclass(frozen=True)
class MarkupAccess:
    company_id: str
    project_id: str
    revision_id: str
    user_id: str
    user_role: str
    site_role: str

    @property
    def can_write(self) -> bool:
        return self.site_role not in _READ_ONLY and self.user_role not in _READ_ONLY


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().strip('"')


def company_for_revision(revision_id: str, user: User) -> str | None:
    found = fetch_access(revision_id, user)
    if found is None or not found.company_id:
        return None
    return found.company_id


def fetch_access(revision_id: str, user: User) -> MarkupAccess | None:
    """revision → sheet → project → membership, one query. Ids come from the path."""
    project = aliased(Record)
    member = aliased(Record)
    access = or_(
        member.user_id == user.id,
        project.owner_id == user.id,
        project.company_key == company_key(user),
    )
    if user.role == "admin":
        access = true()
    stmt = (
        select(
            project.doc_id.label("project_id"),
            project.owner_id.label("owner_id"),
            member.payload["role_on_site"].as_string().label("site_role"),
        )
        .select_from(DrawingRevisionRow)
        .join(
            DrawingRow,
            and_(DrawingRow.id == DrawingRevisionRow.drawing_id, DrawingRow.deleted_at.is_(None)),
        )
        .join(project, and_(project.collection == "projects", project.doc_id == DrawingRow.project_id))
        .outerjoin(
            member,
            and_(
                member.collection == "directory",
                member.project_id == project.doc_id,
                member.user_id == user.id,
            ),
        )
        .where(
            DrawingRevisionRow.id == revision_id,
            DrawingRevisionRow.deleted_at.is_(None),
            DrawingRevisionRow.project_id == DrawingRow.project_id,
            access,
        )
        .limit(1)
    )
    with store._sql.factory() as session:
        row = session.execute(stmt).first()
    if row is None:
        return None
    owner = store.get_user(str(row.owner_id or ""))
    company_id = company_key(owner) if owner is not None else ""
    if not company_id:
        return None
    return MarkupAccess(
        company_id=company_id,
        project_id=str(row.project_id),
        revision_id=revision_id,
        user_id=user.id,
        user_role=_clean(user.role),
        site_role=_clean(row.site_role),
    )


def load_access(revision_id: str, user: User) -> MarkupAccess:
    found = fetch_access(revision_id, user)
    if found is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    ensure_feature(found.company_id, "drawings")
    return found


def _unit(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HTTPException(status_code=400, detail="Некорректные координаты")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise HTTPException(status_code=400, detail="Некорректные координаты")
    return round(number, 6)


def _span(origin: float, size: float) -> float:
    if size <= 0:
        raise HTTPException(status_code=400, detail="Некорректные координаты")
    if origin + size > 1:
        size = round(1 - origin, 6)
    if size <= 0:
        raise HTTPException(status_code=400, detail="Некорректные координаты")
    return size


def _text(value: object) -> str:
    token = " ".join(str(value or "").split())
    if not token or len(token) > 200:
        raise HTTPException(status_code=400, detail="Некорректные данные")
    return token


def _visibility(value: object) -> str:
    token = str(value or "project").strip().lower()
    if token not in {"me", "project"}:
        raise HTTPException(status_code=400, detail="Некорректные данные")
    return token


def _version(value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail="Некорректная версия")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise HTTPException(status_code=400, detail="Некорректная версия")


def clean_shapes(raw: object) -> tuple[list[dict], str | None]:
    if not isinstance(raw, list) or not raw or len(raw) > 8:
        raise HTTPException(status_code=400, detail="Некорректные данные")
    shapes: list[dict] = []
    photo_id: str | None = None
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Некорректные данные")
        kind = str(item.get("type") or "")
        if kind not in _TOOLS:
            raise HTTPException(status_code=400, detail="Некорректные данные")
        if kind == "arrow":
            shapes.append(
                {
                    "type": "arrow",
                    "x1": _unit(item.get("x1")),
                    "y1": _unit(item.get("y1")),
                    "x2": _unit(item.get("x2")),
                    "y2": _unit(item.get("y2")),
                }
            )
        elif kind == "cloud":
            x = _unit(item.get("x"))
            y = _unit(item.get("y"))
            shapes.append(
                {
                    "type": "cloud",
                    "x": x,
                    "y": y,
                    "w": _span(x, _unit(item.get("w"))),
                    "h": _span(y, _unit(item.get("h"))),
                }
            )
        elif kind == "text":
            shapes.append({"type": "text", "x": _unit(item.get("x")), "y": _unit(item.get("y")), "text": _text(item.get("text"))})
        else:
            file_id = parse_uuid(item.get("file_id"))
            if photo_id is not None:
                raise HTTPException(status_code=400, detail="Некорректные данные")
            photo_id = file_id
            x = _unit(item.get("x"))
            y = _unit(item.get("y"))
            shapes.append(
                {
                    "type": "photo",
                    "x": x,
                    "y": y,
                    "w": _span(x, _unit(item.get("w"))),
                    "h": _span(y, _unit(item.get("h"))),
                    "file_id": file_id,
                }
            )
    return shapes, photo_id


def _shape_list(value: object) -> list:
    if isinstance(value, str):
        import json

        value = json.loads(value)
    return value if isinstance(value, list) else []


def _public(row: MarkupRow) -> dict:
    shapes = _shape_list(row.shapes)
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "revision_id": row.revision_id,
        "author_id": row.author_id,
        "file_id": row.file_id,
        "shapes": shapes,
        "visibility": row.visibility,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "row_version": int(row.row_version),
        "deleted_at": row.deleted_at,
    }


def _visible(user_id: str):
    return or_(
        MarkupRow.visibility == "project",
        and_(MarkupRow.visibility == "me", MarkupRow.author_id == user_id),
    )


def _changes(revision_id: str, visibility: str, shapes: list[dict], file_id: str | None) -> dict:
    body = {
        "revision_id": revision_id,
        "visibility": visibility,
        "tools": sorted({item["type"] for item in shapes}),
        "shape_count": len(shapes),
    }
    if file_id:
        body["file_id"] = file_id
    return body


def _stage_photo(access: MarkupAccess, file_id: str | None, raw: bytes | None, stamp: str):
    """Strip and stage before a database session is opened. The key comes from stage_upload."""
    if file_id is None:
        if raw:
            raise HTTPException(status_code=400, detail="Некорректные данные")
        return None, None
    if not raw:
        return None, None
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше лимита")
    try:
        cleaned, mime, _suffix = strip_image(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Только фото") from exc
    storage_key, staged = stage_upload(PHOTO_KIND, cleaned)
    row = StoredFile(
        id=file_id,
        company_id=access.company_id,
        project_id=access.project_id,
        storage_key=storage_key,
        kind=PHOTO_KIND,
        mime=mime,
        size_bytes=len(cleaned),
        sha256=hashlib.sha256(cleaned).hexdigest(),
        meta_stripped=True,
        created_by=access.user_id,
        updated_by=access.user_id,
        created_at=stamp,
        updated_at=stamp,
        row_version=1,
        deleted_at=None,
    )
    return staged, row


def _owned_file(existing: StoredFile, access: MarkupAccess) -> None:
    if (
        existing.deleted_at
        or existing.project_id != access.project_id
        or existing.company_id != access.company_id
        or existing.kind != PHOTO_KIND
        or not existing.meta_stripped
    ):
        raise HTTPException(status_code=404, detail="Не найдено")


def list_for(access: MarkupAccess) -> dict:
    with store._sql.factory() as session:
        rows = session.scalars(
            select(MarkupRow)
            .where(
                MarkupRow.revision_id == access.revision_id,
                MarkupRow.deleted_at.is_(None),
                _visible(access.user_id),
            )
            .order_by(MarkupRow.created_at, MarkupRow.id)
        ).all()
        items = [_public(row) for row in rows]
    return {"can_write": access.can_write, "markups": items}


def save_markup(access: MarkupAccess, payload: dict, raw: bytes | None) -> dict:
    if not access.can_write:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Некорректные данные")
    markup_id = parse_uuid(payload.get("id"))
    assert markup_id is not None
    shapes, photo_id = clean_shapes(payload.get("shapes"))
    visibility = _visibility(payload.get("visibility"))
    row_version = _version(payload.get("row_version"))
    stamp = _now()
    staged, file_row = _stage_photo(access, photo_id, raw, stamp)
    storage_key = file_row.storage_key if file_row is not None else None
    committed = False
    body: dict = {}
    try:
        with store._sql.factory() as session:
            try:
                if photo_id is not None:
                    existing = session.get(StoredFile, photo_id)
                    if existing is not None:
                        discard_upload(staged)
                        staged = None
                        storage_key = None
                        _owned_file(existing, access)
                    elif file_row is None:
                        raise HTTPException(status_code=400, detail="Пустой файл")
                    else:
                        session.add(file_row)
                        session.flush()
                current = session.get(MarkupRow, markup_id)
                if current is None:
                    if row_version not in (0, None):
                        raise MarkupConflict()
                    current = MarkupRow(
                        id=markup_id,
                        company_id=access.company_id,
                        project_id=access.project_id,
                        revision_id=access.revision_id,
                        author_id=access.user_id,
                        file_id=photo_id,
                        shapes=shapes,
                        visibility=visibility,
                        created_by=access.user_id,
                        updated_by=access.user_id,
                        created_at=stamp,
                        updated_at=stamp,
                        row_version=1,
                        deleted_at=None,
                    )
                    session.add(current)
                    session.flush()
                else:
                    if (
                        current.deleted_at
                        or current.revision_id != access.revision_id
                        or current.project_id != access.project_id
                    ):
                        raise HTTPException(status_code=404, detail="Не найдено")
                    if current.visibility == "me" and current.author_id != access.user_id:
                        raise HTTPException(status_code=404, detail="Не найдено")
                    if current.author_id != access.user_id:
                        raise HTTPException(status_code=403, detail="Недостаточно прав")
                    bumped = session.execute(
                        update(MarkupRow)
                        .where(
                            MarkupRow.id == markup_id,
                            MarkupRow.row_version == row_version,
                            MarkupRow.deleted_at.is_(None),
                        )
                        .values(
                            shapes=shapes,
                            visibility=visibility,
                            file_id=photo_id,
                            updated_by=access.user_id,
                            updated_at=stamp,
                            row_version=row_version + 1,
                        )
                    )
                    if bumped.rowcount != 1:
                        session.rollback()
                        raise MarkupConflict()
                    current.shapes = shapes
                    current.visibility = visibility
                    current.file_id = photo_id
                    current.updated_by = access.user_id
                    current.updated_at = stamp
                    current.row_version = row_version + 1
                audit_write(
                    "markup.write",
                    "markup",
                    markup_id,
                    access.project_id,
                    _changes(access.revision_id, visibility, shapes, photo_id),
                    session=session,
                    company_id=access.company_id,
                    actor_user_id=access.user_id,
                )
                body = _public(current)
                session.commit()
                committed = True
            except IntegrityError as exc:
                session.rollback()
                raise MarkupConflict() from exc
    finally:
        if committed and staged is not None and storage_key:
            publish_upload(PHOTO_KIND, storage_key, staged)
        else:
            discard_upload(staged)
    return body


def delete_markup(access: MarkupAccess, markup_id: str, row_version: int) -> dict:
    if not access.can_write:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    token = parse_uuid(markup_id)
    assert token is not None
    stamp = _now()
    with store._sql.factory() as session:
        current = session.get(MarkupRow, token)
        if (
            current is None
            or current.revision_id != access.revision_id
            or current.project_id != access.project_id
            or current.company_id != access.company_id
        ):
            raise HTTPException(status_code=404, detail="Не найдено")
        if current.visibility == "me" and current.author_id != access.user_id:
            raise HTTPException(status_code=404, detail="Не найдено")
        if current.author_id != access.user_id:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        removed = session.execute(
            update(MarkupRow)
            .where(
                MarkupRow.id == token,
                MarkupRow.row_version == row_version,
                MarkupRow.deleted_at.is_(None),
            )
            .values(deleted_at=stamp, updated_at=stamp, updated_by=access.user_id)
        )
        if removed.rowcount != 1:
            session.rollback()
            raise MarkupConflict()
        audit_write(
            "markup.delete",
            "markup",
            token,
            access.project_id,
            {"revision_id": access.revision_id},
            session=session,
            company_id=access.company_id,
            actor_user_id=access.user_id,
        )
        session.commit()
    return {"id": token, "deleted_at": stamp, "row_version": row_version}


def open_file(access: MarkupAccess, file_id: str) -> tuple[Path, str, str]:
    token = parse_uuid(file_id)
    with store._sql.factory() as session:
        found = session.execute(
            select(StoredFile.storage_key, StoredFile.mime, StoredFile.kind)
            .join(MarkupRow, MarkupRow.file_id == StoredFile.id)
            .where(
                StoredFile.id == token,
                StoredFile.company_id == access.company_id,
                StoredFile.project_id == access.project_id,
                StoredFile.kind == PHOTO_KIND,
                StoredFile.deleted_at.is_(None),
                MarkupRow.revision_id == access.revision_id,
                MarkupRow.company_id == access.company_id,
                MarkupRow.project_id == access.project_id,
                MarkupRow.deleted_at.is_(None),
                _visible(access.user_id),
            )
            .limit(1)
        ).first()
    if found is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    storage_key, mime, kind = found
    try:
        path = resolve_stored_file(kind, storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Не найдено") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Не найдено")
    safe_mime = mime or "image/jpeg"
    return path, safe_mime, _DOWNLOAD_NAMES.get(safe_mime, "photo.jpg")
