"""Meeting plans and the tasks they assign.

Rows live in their own tables. Updates compare row_version in SQL and write
the shared audit log in that same transaction. Company id comes from the
project helper. Access is one join: no row means 404.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.audit import write as audit_write
from app.company_features import ensure_feature, resolve_path_company
from app.meeting_schema import ActionItemRow, MeetingParticipantRow, MeetingRow
from app.schemas import User
from app.site_models import Project
from app.sql_backend import Record
from app.store import store
from app.tenant import company_key

PUSH_TEXT = "Новое событие по объекту"
pushes: list[dict[str, str]] = []

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+\d|\d)[\d\s().-]{7,}\d")
_SOURCES = {"meeting", "punch", "rfi"}
_ALLOWED = {("open", "done"), ("open", "cancelled")}
_KNOWN_ROLES = {
    "owner",
    "foreman",
    "supervisor",
    "procurement",
    "customer",
    "supplier",
    "moderator",
    "contractor",
    "buyer",
}


class Conflict(Exception):
    def __init__(self, detail: str = "Изменено другим") -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass
class Access:
    user: User
    project: Project
    company_id: str
    meeting: dict | None = None
    item: dict | None = None


def note_push(event_id: str) -> dict[str, str]:
    payload = {"text": PUSH_TEXT, "id": event_id}
    pushes.append(payload)
    return payload


def redact(value: str) -> str:
    return _PHONE.sub("***", value or "")


def protocol_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with no author metadata."""
    safe = [redact(line).encode("latin-1", "replace").decode("latin-1") for line in lines]
    commands = ["BT", "/F1 12 Tf", "48 780 Td", "16 TL"]
    for index, line in enumerate(safe or [""]):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index == 0:
            commands.append(f"({escaped}) Tj")
        else:
            commands.append(f"T* ({escaped}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    objects[3] = b"4 0 obj\n" + objects[3] + b"\nendobj\n"
    header = b"%PDF-1.4\n"
    body = b""
    offsets = [0]
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        body += obj
        cursor += len(obj)
    xref = [f"xref\n0 {len(offsets)}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{cursor}\n%%EOF\n".encode("ascii")
    )
    return header + body + b"".join(xref) + trailer


def _stamp() -> str:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    if stamp.endswith("Z"):
        return stamp[:-1] + "+00:00"
    return stamp


def _open_access(project, user: User):
    """Same membership test as resolve_path_company: directory, owner, or stored company."""
    member = aliased(Record)
    access = or_(
        member.user_id == user.id,
        project.owner_id == user.id,
        project.company_key == company_key(user),
    )
    if user.role == "admin":
        access = true()
    return member, access


def _stored_company(owner_id: object) -> str:
    """Same tenant id as resolve_path_company: the project owner's stored key."""
    owner = store.get_user(str(owner_id or ""))
    resolved = company_key(owner) if owner is not None else ""
    if not resolved:
        raise HTTPException(status_code=404, detail="Не найдено")
    ensure_feature(resolved, "meetings")
    return resolved


def access_project(pid: str, user: User) -> Access:
    company_id = resolve_path_company("projects", pid, user)
    if not company_id:
        raise HTTPException(status_code=404, detail="Не найдено")
    project = store.get_project(pid)
    if project is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    ensure_feature(company_id, "meetings")
    return Access(user=user, project=project, company_id=company_id)


def _load_entity(model, entity_id: str, user: User):
    project = aliased(Record)
    member, access = _open_access(project, user)
    stmt = (
        select(model, project.owner_id, project.payload)
        .join(project, and_(project.collection == "projects", project.doc_id == model.project_id))
        .outerjoin(
            member,
            and_(
                member.collection == "directory",
                member.project_id == project.doc_id,
                member.user_id == user.id,
            ),
        )
        .where(model.id == entity_id, model.deleted_at.is_(None), access)
        .limit(1)
    )
    with store._sql.factory() as session:
        found = session.execute(stmt).first()
        if found is None:
            return None
        row, owner_id, payload = found
        public = _meeting_public(row) if model is MeetingRow else _action_public(row)
        return public, owner_id, payload


def access_meeting(mid: str, user: User) -> Access:
    found = _load_entity(MeetingRow, mid, user)
    if found is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    meeting, owner_id, payload = found
    project = Project.model_validate(payload)
    access = Access(user=user, project=project, company_id=_stored_company(owner_id))
    access.meeting = meeting
    return access


def access_action(aid: str, user: User) -> Access:
    found = _load_entity(ActionItemRow, aid, user)
    if found is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    item, owner_id, payload = found
    project = Project.model_validate(payload)
    access = Access(user=user, project=project, company_id=_stored_company(owner_id))
    access.item = item
    return access


def assignee_choices(project: Project) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()

    def add(user_id: str | None, role: str) -> None:
        if not user_id or user_id in seen:
            return
        person = store.get_user(user_id)
        if person is None:
            return
        seen.add(user_id)
        rows.append({"user_id": person.id, "name": person.full_name, "role": role})

    add(project.owner_id, "owner")
    add(project.contractor_id, "contractor")
    for row in store.directory.values():
        if row.project_id == project.id:
            add(row.user_id, row.role_on_site or "member")
    return rows


def member_ids(project: Project) -> set[str]:
    return {row["user_id"] for row in assignee_choices(project)}


def project_bundle(project: Project) -> tuple[list[dict], list[dict], list[dict]]:
    with store._sql.factory() as session:
        meetings = session.scalars(
            select(MeetingRow)
            .where(MeetingRow.project_id == project.id, MeetingRow.deleted_at.is_(None))
            .order_by(MeetingRow.meeting_date.desc(), MeetingRow.id)
        ).all()
        items = session.scalars(
            select(ActionItemRow)
            .where(ActionItemRow.project_id == project.id, ActionItemRow.deleted_at.is_(None))
            .order_by(ActionItemRow.due_date.asc(), ActionItemRow.id)
        ).all()
        plans = [_meeting_public(row) for row in meetings]
        tasks = [_action_public(row) for row in items]
    return plans, tasks, assignee_choices(project)


def tasks_for_assignee(assignee_id: str, status: str, project_id: str) -> list[dict]:
    """Hot path for My tasks: (assignee_id, status, due_date)."""
    with store._sql.factory() as session:
        rows = session.scalars(
            select(ActionItemRow)
            .where(
                ActionItemRow.assignee_id == assignee_id,
                ActionItemRow.status == status,
                ActionItemRow.project_id == project_id,
                ActionItemRow.deleted_at.is_(None),
            )
            .order_by(ActionItemRow.due_date.asc(), ActionItemRow.id.asc())
        ).all()
        public = [_action_public(row) for row in rows]
    superseded = {row["carried_from_id"] for row in public if row.get("carried_from_id")}
    return [row for row in public if row["id"] not in superseded]


def create_plan(access: Access, body: dict) -> dict:
    company_id = access.company_id
    project = access.project
    meeting_id = _uuid(body.get("id"))
    day = _day(str(body.get("day") or ""), required=False)
    title = str(body.get("title") or "").strip() or day
    if len(title) > 200:
        raise ValueError("Тема слишком длинная")
    agenda = str(body.get("agenda") or "").strip()
    if len(agenda) > 4000:
        raise ValueError("Повестка слишком длинная")
    raw_items = list(body.get("action_items") or [])
    prepared = [_prepare_item(raw, meeting_id) for raw in raw_items]
    allowed = member_ids(project)
    participants = list(dict.fromkeys(str(value).strip() for value in (body.get("participants") or []) if str(value).strip()))
    for item in prepared:
        if item["assignee_id"] not in participants:
            participants.append(item["assignee_id"])
    if not participants and not prepared:
        participants = [access.user.id] if access.user.id in allowed else []
    unknown = [user_id for user_id in participants if user_id not in allowed]
    if unknown:
        raise ValueError("Участник не состоит в объекте")
    for item in prepared:
        if item["assignee_id"] not in allowed:
            raise ValueError("Исполнитель не состоит в объекте")
    now = _stamp()
    session = store._sql.factory()
    try:
        if session.get(MeetingRow, meeting_id) is not None:
            raise Conflict()
        carried = _carry_copies(session, project.id, meeting_id, company_id, now, access.user.id)
        for item in prepared:
            if session.get(ActionItemRow, item["id"]) is not None:
                raise Conflict()
        meeting = MeetingRow(
            id=meeting_id,
            company_id=company_id,
            project_id=project.id,
            title=title,
            meeting_date=day,
            agenda=agenda,
            decisions="",
            participants=participants,
            created_at=now,
            updated_at=now,
            created_by=access.user.id,
            updated_by=access.user.id,
            row_version=1,
            deleted_at=None,
        )
        session.add(meeting)
        for user_id in participants:
            session.add(
                MeetingParticipantRow(
                    id=str(uuid4()),
                    company_id=company_id,
                    project_id=project.id,
                    meeting_id=meeting_id,
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                    created_by=access.user.id,
                    updated_by=access.user.id,
                    row_version=1,
                    deleted_at=None,
                )
            )
        stored: list[ActionItemRow] = []
        for item in prepared:
            row = _new_action(item, company_id, project.id, meeting_id, now, access.user.id, carried_from_id=None)
            session.add(row)
            stored.append(row)
            audit_write(
                "meeting.action_item.create",
                "action_item",
                row.id,
                project.id,
                {"status": ["", "open"], "source": row.source},
                company_id=company_id,
                actor_user_id=access.user.id,
                session=session,
            )
        for row in carried:
            session.add(row)
            stored.append(row)
            audit_write(
                "meeting.action_item.carry",
                "action_item",
                row.id,
                project.id,
                {"carried_from_id": row.carried_from_id or ""},
                company_id=company_id,
                actor_user_id=access.user.id,
                session=session,
            )
        audit_write(
            "meeting.create",
            "meeting",
            meeting_id,
            project.id,
            {"row_version": [0, 1]},
            company_id=company_id,
            actor_user_id=access.user.id,
            session=session,
        )
        session.commit()
        data = {"meeting": _meeting_public(meeting), "action_items": [_action_public(row) for row in stored]}
    except IntegrityError as exc:
        session.rollback()
        raise Conflict() from exc
    except Conflict:
        session.rollback()
        raise
    finally:
        session.close()
    note_push(meeting_id)
    return data


def set_status(access: Access, status: str, row_version: int) -> dict:
    item = access.item or {}
    current = str(item.get("status") or "")
    if (current, status) not in _ALLOWED:
        raise Conflict("Этот переход статуса недоступен")
    now = _stamp()
    action = "meeting.action_item.close" if status == "done" else "meeting.action_item.cancel"
    return _cas(
        access,
        {"status": status, "updated_at": now, "updated_by": access.user.id, "row_version": row_version + 1},
        row_version,
        action,
        {"status": [current, status]},
    )


def tombstone(access: Access, row_version: int) -> dict:
    now = _stamp()
    return _cas(
        access,
        {"deleted_at": now, "updated_at": now, "updated_by": access.user.id, "row_version": row_version + 1},
        row_version,
        "record.delete",
        {"deleted_at": ["", "set"]},
    )


def meeting_file(access: Access) -> bytes:
    meeting = access.meeting or {}
    items = _items_for_meeting(meeting["id"])
    roles = {row["user_id"]: row["role"] for row in assignee_choices(access.project)}
    lines = [str(meeting.get("title") or ""), str(meeting.get("meeting_date") or ""), redact(str(meeting.get("agenda") or ""))]
    for item in items:
        role = roles.get(item.get("assignee_id") or "", "")
        label = role if role in _KNOWN_ROLES else "member"
        lines.append(redact(f"{item.get('text') or ''} · {label} · {item.get('due_date') or ''}"))
    return protocol_pdf([line for line in lines if line])


def meeting_links(access: Access) -> dict:
    meeting = access.meeting or {}
    user_ids = [str(value) for value in (meeting.get("participants") or [])]
    for item in _items_for_meeting(meeting["id"]):
        assignee = str(item.get("assignee_id") or "")
        if assignee and assignee not in user_ids:
            user_ids.append(assignee)
    return {"user_ids": user_ids}


def _cas(access: Access, values: dict, row_version: int, action: str, changes: dict) -> dict:
    item = access.item or {}
    session = store._sql.factory()
    try:
        result = session.execute(
            update(ActionItemRow)
            .where(
                ActionItemRow.id == item["id"],
                ActionItemRow.row_version == row_version,
                ActionItemRow.deleted_at.is_(None),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            session.rollback()
            raise Conflict()
        audit_write(
            action,
            "action_item",
            item["id"],
            access.project.id,
            changes,
            company_id=access.company_id,
            actor_user_id=access.user.id,
            session=session,
        )
        session.commit()
        row = session.get(ActionItemRow, item["id"])
        if row is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        return _action_public(row)
    except Conflict:
        session.rollback()
        raise
    finally:
        session.close()


def _carry_copies(session, project_id: str, meeting_id: str, company_id: str, now: str, actor: str) -> list[ActionItemRow]:
    rows = session.scalars(
        select(ActionItemRow).where(
            ActionItemRow.project_id == project_id,
            ActionItemRow.deleted_at.is_(None),
            ActionItemRow.status == "open",
        )
    ).all()
    superseded = {row.carried_from_id for row in rows if row.carried_from_id}
    copies: list[ActionItemRow] = []
    for row in rows:
        if row.id in superseded:
            continue
        copies.append(
            ActionItemRow(
                id=str(uuid4()),
                company_id=company_id,
                project_id=project_id,
                meeting_id=meeting_id,
                text=row.text,
                assignee_id=row.assignee_id,
                due_date=row.due_date,
                status="open",
                source=row.source,
                source_id=row.source_id,
                carried_from_id=row.id,
                created_at=now,
                updated_at=now,
                created_by=actor,
                updated_by=actor,
                row_version=1,
                deleted_at=None,
            )
        )
    return copies


def _new_action(
    item: dict,
    company_id: str,
    project_id: str,
    meeting_id: str,
    now: str,
    actor: str,
    carried_from_id: str | None,
) -> ActionItemRow:
    return ActionItemRow(
        id=item["id"],
        company_id=company_id,
        project_id=project_id,
        meeting_id=meeting_id,
        text=item["text"],
        assignee_id=item["assignee_id"],
        due_date=item["due_date"],
        status="open",
        source=item["source"],
        source_id=item["source_id"],
        carried_from_id=carried_from_id,
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
        row_version=1,
        deleted_at=None,
    )


def _prepare_item(raw: dict, meeting_id: str) -> dict:
    text_value = str(raw.get("text") or "").strip()
    if len(text_value) < 1 or len(text_value) > 500:
        raise ValueError("Укажите поручение")
    assignee_id = str(raw.get("assignee_id") or "").strip()
    if not assignee_id:
        raise ValueError("Укажите исполнителя")
    due = _day(str(raw.get("due_date") or raw.get("due") or ""), required=True)
    source = str(raw.get("source") or "meeting").strip()
    if source not in _SOURCES:
        raise ValueError("Неизвестный источник")
    source_id = str(raw.get("source_id") or "").strip() or (meeting_id if source == "meeting" else "")
    return {
        "id": _uuid(raw.get("id")),
        "text": text_value,
        "assignee_id": assignee_id,
        "due_date": due,
        "source": source,
        "source_id": source_id or None,
    }


def _items_for_meeting(meeting_id: str) -> list[dict]:
    with store._sql.factory() as session:
        rows = session.scalars(
            select(ActionItemRow)
            .where(ActionItemRow.meeting_id == meeting_id, ActionItemRow.deleted_at.is_(None))
            .order_by(ActionItemRow.due_date.asc(), ActionItemRow.id)
        ).all()
        return [_action_public(row) for row in rows]


def _uuid(value: object) -> str:
    if value is None or str(value).strip() == "":
        return str(uuid4())
    token = str(value).strip().lower()
    if not _UUID.match(token):
        raise ValueError("Некорректный идентификатор")
    return str(UUID(token))


def _day(value: str, *, required: bool) -> str:
    text_value = value.strip()
    if not text_value:
        if required:
            raise ValueError("Укажите срок")
        return datetime.now(UTC).date().isoformat()
    try:
        datetime.strptime(text_value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Укажите дату") from exc
    return text_value


def _meeting_public(row: MeetingRow) -> dict:
    participants = row.participants if isinstance(row.participants, list) else []
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "title": row.title,
        "day": row.meeting_date,
        "meeting_date": row.meeting_date,
        "agenda": row.agenda,
        "decisions": row.decisions,
        "participants": [str(value) for value in participants],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "row_version": int(row.row_version),
        "deleted_at": row.deleted_at,
    }


def _action_public(row: ActionItemRow) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "meeting_id": row.meeting_id,
        "text": row.text,
        "assignee_id": row.assignee_id,
        "due_date": row.due_date,
        "status": row.status,
        "source": row.source,
        "source_id": row.source_id,
        "carried_from_id": row.carried_from_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "row_version": int(row.row_version),
        "deleted_at": row.deleted_at,
    }
