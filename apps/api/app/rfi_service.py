"""Designer questions stored in their own tables.

Writes use compare-and-swap on row_version. Personal data of an external
recipient lives in external_contacts, not on the question.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app import audit
from app.company_features import project_company_id
from app.media import strip_image, strip_pdf_author
from app.paths import resolve_stored_file, write_stored_file
from app.rfi_tables import access_tokens, external_contacts, rfis
from app.shares import hashes_match, new_share_token, parse_expiry, token_hash
from app.store import store

PUSH_BODY = "Новое событие по объекту"
RFI_MIN_DAYS = 14
RFI_MAX_DAYS = 30
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_REVISION = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_CLOSE_FROM = {"open", "answered"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _today() -> date:
    return datetime.now(UTC).date()


def add_business_days(start: date, days: int = 5) -> date:
    left = days
    cursor = start
    while left > 0:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            left -= 1
    return cursor


def push_payload(entity_id: str) -> dict:
    return {"body": PUSH_BODY, "id": entity_id}


def _uuid(value: str, label: str = "id") -> str:
    if not value or not _UUID.match(value):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    return value.lower()


def _member(project, user_id: str) -> bool:
    if project is not None and project.owner_id == user_id:
        return True
    return any(
        row.project_id == getattr(project, "id", "") and row.user_id == user_id for row in store.directory.values()
    )


def _phone_hash(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()


def _due(value: str | None) -> str:
    if not value:
        return add_business_days(_today(), 5).isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректная дата") from exc


def _revision(value: str | None) -> str | None:
    text_value = (value or "").strip()
    if not text_value:
        return None
    if not _REVISION.match(text_value):
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    return text_value


def _attachments(raw: str | None) -> list[str]:
    try:
        loaded = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if item]


def _overdue(status: str, due: str | None, today: date | None = None) -> bool:
    if status != "open" or not due:
        return False
    try:
        parsed = date.fromisoformat(due)
    except ValueError:
        return False
    return parsed < (today or _today())


def _contact_view(row, viewer_id: str) -> dict | None:
    if row is None or row.author_id != viewer_id or row.deleted_at:
        return None
    return {
        "id": row.id,
        "full_name": row.full_name or "",
        "phone": row.phone_e164 or "",
        "email": row.email or "",
        "organization": row.organization or "",
    }


def _view(row, viewer_id: str, contact=None) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "number": row.number,
        "title": row.title,
        "question": row.question,
        "answer": row.answer or "",
        "status": row.status,
        "due_date": row.due_date,
        "assignee_user_id": row.assignee_user_id,
        "assignee_contact_id": row.assignee_contact_id,
        "drawing_revision_id": row.drawing_revision_id,
        "attachments": _attachments(row.attachments),
        "author_id": row.author_id,
        "answered_at": row.answered_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "row_version": int(row.row_version),
        "deleted_at": row.deleted_at,
        "overdue": _overdue(row.status, row.due_date),
        "contact": _contact_view(contact, viewer_id) if contact is not None and row.author_id == viewer_id else None,
    }


def _load(session, rfi_id: str):
    return session.execute(select(rfis).where(rfis.c.id == rfi_id)).mappings().first()


def _load_contact(session, contact_id: str | None):
    if not contact_id:
        return None
    return session.execute(select(external_contacts).where(external_contacts.c.id == contact_id)).mappings().first()


def count_open(project_id: str) -> int:
    try:
        with store._sql.factory() as session:
            found = session.scalar(
                select(func.count())
                .select_from(rfis)
                .where(rfis.c.project_id == project_id, rfis.c.status == "open", rfis.c.deleted_at.is_(None))
            )
            return int(found or 0)
    except (OperationalError, ProgrammingError):
        return 0


def list_for_user(user, project_id: str) -> list[dict]:
    with store._sql.factory() as session:
        rows = session.execute(
            select(rfis)
            .where(rfis.c.project_id == project_id, rfis.c.deleted_at.is_(None))
            .order_by(rfis.c.created_at)
        ).mappings().all()
        contact_ids = [row.assignee_contact_id for row in rows if row.assignee_contact_id and row.author_id == user.id]
        contacts = {}
        if contact_ids:
            found = session.execute(
                select(external_contacts).where(external_contacts.c.id.in_(contact_ids))
            ).mappings().all()
            contacts = {row.id: row for row in found}
        return [_view(row, user.id, contacts.get(row.assignee_contact_id)) for row in rows]


def create_rfi(user, access: dict, body: dict) -> dict:
    project = store.get_project(access["project_id"])
    if project is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    company_id = project_company_id(project)
    if not company_id or company_id != access["company_id"]:
        raise HTTPException(status_code=404, detail="Не найдено")
    record_id = _uuid(str(body.get("id") or ""))
    question = str(body.get("question") or "").strip()
    title = str(body.get("title") or "").strip() or question[:80]
    if not question or not title:
        raise HTTPException(status_code=400, detail="Укажите вопрос")
    if len(title) > 200 or len(question) > 4000:
        raise HTTPException(status_code=400, detail="Слишком длинный текст")
    sent_version = body.get("row_version")
    if sent_version not in (None, 0, 1):
        raise HTTPException(status_code=409, detail="Изменено другим")
    assignee = str(body.get("assignee_user_id") or "").strip() or None
    contact_body = body.get("contact")
    if assignee and contact_body:
        raise HTTPException(status_code=400, detail="Укажите одного адресата")
    if assignee and not _member(project, assignee):
        raise HTTPException(status_code=404, detail="Не найдено")
    due = _due(body.get("due_date"))
    revision = _revision(body.get("drawing_revision_id"))
    stamp = _now()
    contact_id = None
    session = store._sql.factory()
    try:
        if contact_body:
            contact_id = _uuid(str(contact_body.get("id") or ""), "contact")
            phone = str(contact_body.get("phone") or "").strip()[:32]
            session.execute(
                external_contacts.insert().values(
                    id=contact_id,
                    company_id=company_id,
                    project_id=project.id,
                    author_id=user.id,
                    full_name=str(contact_body.get("full_name") or "").strip()[:200] or None,
                    phone_e164=phone or None,
                    phone_hash=_phone_hash(phone),
                    email=str(contact_body.get("email") or "").strip()[:200] or None,
                    organization=str(contact_body.get("organization") or "").strip()[:200] or None,
                    created_at=stamp,
                    updated_at=stamp,
                    row_version=1,
                    deleted_at=None,
                )
            )
        number = int(
            session.scalar(select(func.count()).select_from(rfis).where(rfis.c.project_id == project.id)) or 0
        )
        session.execute(
            rfis.insert().values(
                id=record_id,
                company_id=company_id,
                project_id=project.id,
                number=f"RFI-{number + 1:03d}",
                title=title,
                question=question,
                answer="",
                status="open",
                assignee_user_id=assignee,
                assignee_contact_id=contact_id,
                due_date=due,
                drawing_revision_id=revision,
                attachments="[]",
                author_id=user.id,
                answered_at=None,
                answered_via_token_id=None,
                created_at=stamp,
                updated_at=stamp,
                row_version=1,
                deleted_at=None,
            )
        )
        audit.write(
            session,
            "rfi.create",
            "rfi",
            record_id,
            project.id,
            {"status": "open", "due_date": due, "drawing_revision_id": revision, "assignee_user_id": assignee},
            company_id=company_id,
            actor=user.id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    finally:
        session.close()
    with store._sql.factory() as session:
        row = _load(session, record_id)
        contact = _load_contact(session, contact_id)
    data = _view(row, user.id, contact)
    data["push"] = push_payload(record_id)
    return data


def _conflict():
    raise HTTPException(status_code=409, detail="Изменено другим")


def _cas(session, rfi_id: str, version: int, values: dict) -> None:
    result = session.execute(
        update(rfis)
        .where(rfis.c.id == rfi_id, rfis.c.row_version == version, rfis.c.deleted_at.is_(None))
        .values(**values, row_version=version + 1, updated_at=_now())
    )
    if result.rowcount != 1:
        session.rollback()
        _conflict()


def answer_rfi(
    user,
    rfi_id: str,
    answer: str,
    row_version: int,
    *,
    token_id: str | None = None,
    token_version: int | None = None,
) -> dict:
    text_value = (answer or "").strip()
    if not text_value:
        raise HTTPException(status_code=400, detail="Укажите ответ")
    if len(text_value) > 4000:
        raise HTTPException(status_code=400, detail="Слишком длинный текст")
    session = store._sql.factory()
    try:
        row = _load(session, rfi_id)
        if row is None or row.deleted_at:
            session.rollback()
            raise HTTPException(status_code=404, detail="Не найдено")
        if row.status != "open":
            session.rollback()
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        stamp = _now()
        _cas(
            session,
            rfi_id,
            int(row_version),
            {
                "answer": text_value,
                "status": "answered",
                "answered_at": stamp,
                "answered_via_token_id": token_id,
            },
        )
        if token_id is not None:
            spent = session.execute(
                update(access_tokens)
                .where(
                    access_tokens.c.id == token_id,
                    access_tokens.c.used_at.is_(None),
                    access_tokens.c.row_version == int(token_version or 0),
                )
                .values(used_at=stamp, row_version=int(token_version or 0) + 1, updated_at=stamp)
            )
            if spent.rowcount != 1:
                session.rollback()
                raise HTTPException(status_code=410, detail="Срок ссылки истёк")
        audit.write(
            session,
            "rfi.answer",
            "rfi",
            rfi_id,
            row.project_id,
            {"status": ["open", "answered"], "answer": text_value},
            company_id=row.company_id,
            actor=user.id if user is not None else "link",
        )
        session.commit()
    finally:
        session.close()
    with store._sql.factory() as session:
        saved = _load(session, rfi_id)
        contact = _load_contact(session, saved.assignee_contact_id)
    viewer = user.id if user is not None else ""
    data = _view(saved, viewer, contact)
    data["push"] = push_payload(rfi_id)
    return data


def set_status(user, rfi_id: str, status: str, row_version: int) -> dict:
    if status != "closed":
        raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
    session = store._sql.factory()
    try:
        row = _load(session, rfi_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        if row.status not in _CLOSE_FROM:
            session.rollback()
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        previous = row.status
        _cas(session, rfi_id, int(row_version), {"status": "closed"})
        audit.write(
            session,
            "rfi.status_change",
            "rfi",
            rfi_id,
            row.project_id,
            {"status": [previous, "closed"]},
            company_id=row.company_id,
            actor=user.id,
        )
        session.commit()
    finally:
        session.close()
    with store._sql.factory() as session:
        saved = _load(session, rfi_id)
        contact = _load_contact(session, saved.assignee_contact_id)
    return _view(saved, user.id, contact)


def tombstone(user, rfi_id: str, row_version: int) -> dict:
    session = store._sql.factory()
    try:
        row = _load(session, rfi_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        stamp = _now()
        _cas(session, rfi_id, int(row_version), {"deleted_at": stamp})
        audit.write(
            session,
            "rfi.delete",
            "rfi",
            rfi_id,
            row.project_id,
            {"row_version": int(row_version) + 1},
            company_id=row.company_id,
            actor=user.id,
        )
        session.commit()
    finally:
        session.close()
    return {"id": rfi_id, "deleted_at": stamp}


def read_for_user(user, rfi_id: str) -> dict:
    with store._sql.factory() as session:
        row = _load(session, rfi_id)
        if row is None or row.deleted_at:
            raise HTTPException(status_code=404, detail="Не найдено")
        contact = _load_contact(session, row.assignee_contact_id)
        return _view(row, user.id, contact)


def attach_file(user, access: dict, rfi_id: str, file_id: str, raw: bytes, content_type: str | None, row_version: int) -> dict:
    record_file = _uuid(file_id)
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if raw.startswith(b"%PDF") or declared == "application/pdf":
        cleaned = strip_pdf_author(raw)
        media_type = "application/pdf"
        suffix = "pdf"
    else:
        cleaned, media_type, suffix = strip_image(raw)
        suffix = suffix.lstrip(".")
    digest = hashlib.sha256(cleaned).hexdigest()
    stored_name = f"{access['project_id']}/{record_file}.{suffix}"
    write_stored_file("upload", stored_name, cleaned)
    store.add_upload(
        user,
        stored_name,
        media_type,
        access["project_id"],
        kind="upload",
        file_id=record_file,
        size=len(cleaned),
        sha256=digest,
    )
    session = store._sql.factory()
    try:
        row = _load(session, rfi_id)
        if row is None or row.deleted_at or row.project_id != access["project_id"]:
            raise HTTPException(status_code=404, detail="Не найдено")
        if int(row.row_version) != int(row_version):
            session.rollback()
            _conflict()
        files = _attachments(row.attachments)
        if record_file not in files:
            files.append(record_file)
        _cas(session, rfi_id, int(row_version), {"attachments": json.dumps(files)})
        audit.write(
            session,
            "rfi.file",
            "rfi",
            rfi_id,
            row.project_id,
            {"file_id": record_file},
            company_id=row.company_id,
            actor=user.id,
        )
        session.commit()
    finally:
        session.close()
    with store._sql.factory() as session:
        saved = _load(session, rfi_id)
        contact = _load_contact(session, saved.assignee_contact_id)
    data = _view(saved, user.id, contact)
    data["file_id"] = record_file
    return data


def read_file(project_id: str, rfi_id: str, file_id: str) -> tuple[str, str]:
    with store._sql.factory() as session:
        row = _load(session, rfi_id)
    if row is None or row.deleted_at or row.project_id != project_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    if file_id not in _attachments(row.attachments):
        raise HTTPException(status_code=404, detail="Не найдено")
    stored = store.get_upload(file_id)
    if stored is None or stored.project_id != project_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    try:
        path = resolve_stored_file(stored.kind, stored.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Не найдено") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Не найдено")
    return str(path), stored.content_type


def create_link(user, access: dict, rfi_id: str, body: dict) -> dict:
    days = int(body.get("expires_in_days") or RFI_MIN_DAYS)
    if days < RFI_MIN_DAYS or days > RFI_MAX_DAYS:
        raise HTTPException(status_code=400, detail="Срок ссылки от 14 до 30 дней")
    link_id = _uuid(str(body.get("id") or ""))
    token = new_share_token()
    expires = datetime.now(UTC) + timedelta(days=days)
    stamp = _now()
    session = store._sql.factory()
    try:
        row = _load(session, rfi_id)
        if row is None or row.deleted_at or row.project_id != access["project_id"]:
            raise HTTPException(status_code=404, detail="Не найдено")
        if row.status != "open":
            raise HTTPException(status_code=409, detail="Этот переход статуса недоступен")
        session.execute(
            access_tokens.insert().values(
                id=link_id,
                company_id=access["company_id"],
                project_id=access["project_id"],
                purpose="rfi_reply",
                token_sha256=token_hash(token),
                entity_id=rfi_id,
                expires_at=expires.isoformat(timespec="seconds"),
                used_at=None,
                created_by=user.id,
                created_at=stamp,
                updated_at=stamp,
                row_version=1,
                deleted_at=None,
            )
        )
        audit.write(
            session,
            "rfi.link",
            "rfi",
            rfi_id,
            access["project_id"],
            {"expires_in_days": days},
            company_id=access["company_id"],
            actor=user.id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Изменено другим") from exc
    finally:
        session.close()
    return {"id": link_id, "token": token, "expires_at": expires.isoformat(timespec="seconds")}


def _token_row(token: str):
    if not token or len(token) < 20:
        return None, 404
    digest = token_hash(token)
    with store._sql.factory() as session:
        rows = session.execute(
            select(access_tokens).where(
                access_tokens.c.token_sha256 == digest,
                access_tokens.c.purpose == "rfi_reply",
                access_tokens.c.deleted_at.is_(None),
            )
        ).mappings().all()
    match = next((row for row in rows if hashes_match(row.token_sha256, digest)), None)
    if match is None:
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
        ensure_feature(row.company_id, "rfi")
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="Ссылка не найдена") from exc
    return row


def public_read(token: str) -> dict:
    link = _public_or_error(token, writing=False)
    with store._sql.factory() as session:
        row = _load(session, link.entity_id)
    if row is None or row.deleted_at:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    project = store.get_project(row.project_id)
    return {
        "number": row.number,
        "title": row.title,
        "question": row.question,
        "answer": row.answer or "",
        "status": row.status,
        "due_date": row.due_date,
        "project_title": project.title if project is not None else "",
        "attachments": [{"id": file_id} for file_id in _attachments(row.attachments)],
        "answered": bool(link.used_at) or row.status != "open",
    }


def public_answer(token: str, answer: str) -> dict:
    link = _public_or_error(token, writing=True)
    with store._sql.factory() as session:
        current = _load(session, link.entity_id)
    if current is None or current.deleted_at:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    data = answer_rfi(
        None,
        current.id,
        answer,
        int(current.row_version),
        token_id=link.id,
        token_version=int(link.row_version),
    )
    return {"status": data["status"], "answer": data["answer"]}


def public_file(token: str, file_id: str) -> tuple[str, str]:
    link = _public_or_error(token, writing=False)
    with store._sql.factory() as session:
        row = _load(session, link.entity_id)
    if row is None or row.deleted_at or file_id not in _attachments(row.attachments):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return read_file(row.project_id, row.id, file_id)


def render_pdf(user, rfi_id: str) -> bytes:
    data = read_for_user(user, rfi_id)
    lines = [
        data["number"],
        data["status"],
        data["due_date"] or "",
        data["question"],
        data["answer"],
    ]
    font = ImageFont.truetype(_FONT, 22)
    image = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(image)
    y = 48
    for line in lines:
        for chunk in _wrap(line, 48):
            draw.text((48, y), chunk, fill="black", font=font)
            y += 36
            if y > 1120:
                break
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return _pdf_with_jpeg(out.getvalue(), image.size[0], image.size[1])


def _wrap(value: str, width: int) -> list[str]:
    text_value = (value or "").replace("\n", " ").strip()
    if not text_value:
        return [""]
    words = text_value.split()
    rows: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if len(trial) > width and current:
            rows.append(current)
            current = word
        else:
            current = trial
    if current:
        rows.append(current)
    return rows


def _pdf_with_jpeg(jpeg: bytes, width: int, height: int) -> bytes:
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
