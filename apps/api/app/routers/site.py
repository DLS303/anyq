import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.company_features import (
    apply_bundle_flags,
    feature_open_for_company,
    flag_map,
    project_company_id,
    require_feature,
)
from app.deps import require_user
from app.idempotency import IdempotencyConflict, run_idempotent
from app.paths import write_stored_file
from app.photo_jobs import (
    PHOTO_POOL,
    create_job,
    get_job,
    mark,
    photo_timeout,
    process_in_pool,
)
from app.schemas import User
from app.shares import (
    DEFAULT_SHARE_DAYS,
    MAX_SHARE_DAYS,
    MIN_SHARE_DAYS,
    member_daily,
    new_share_token,
    share_is_active,
    token_hash,
)
from app.site_models import DailyPhoto, LogWeather, MemberRole, Project, VoiceNote
from app.store import store

router = APIRouter(prefix="/v1/site", tags=["site"])


MAX_VOICE_BYTES = 2 * 1024 * 1024
_AUDIO_TYPES = {
    "audio/webm",
    "video/webm",
    "audio/ogg",
    "application/ogg",
    "audio/mp4",
    "video/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "application/octet-stream",
}


class DailyIn(BaseModel):
    day: str
    weather: LogWeather = "clear"
    temp_c: int | None = None
    workers: int = 0
    notes: str = ""
    delays: str = ""
    delay_hours: float = Field(default=0, ge=0, le=24)


class ProjectIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    address: str = Field(default="", max_length=200)
    deadline: str | None = None
    budget_kzt: int | None = None


class MemberIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    role: MemberRole


def _audio_file(data: bytes, content_type: str | None) -> tuple[str, str]:
    if not data:
        raise ValueError("Пустой аудиофайл")
    if len(data) > MAX_VOICE_BYTES:
        raise ValueError("Аудио больше 2 МБ")
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared and declared not in _AUDIO_TYPES:
        raise ValueError("Нужен аудиофайл webm, ogg или mp4")
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm", "webm"
    if data.startswith(b"OggS"):
        return "audio/ogg", "ogg"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "audio/mp4", "m4a"
    raise ValueError("Нужен аудиофайл webm, ogg или mp4")


def _required_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Укажите название")
    return text


class ShareIn(BaseModel):
    expires_in_days: int = Field(default=DEFAULT_SHARE_DAYS, ge=MIN_SHARE_DAYS, le=MAX_SHARE_DAYS)


class RfiIn(BaseModel):
    title: str
    question: str
    drawing: str = ""
    assignee_id: str | None = None

    @field_validator("title", "question")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _required_text(value)


class AnswerIn(BaseModel):
    answer: str


class PunchIn(BaseModel):
    title: str
    location: str = ""
    trade: str = ""
    photo: str = ""

    @field_validator("title")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _required_text(value)


class StatusIn(BaseModel):
    status: str


class CheckItemIn(BaseModel):
    label: str
    result: str
    comment: str = ""


class InspIn(BaseModel):
    title: str
    checklist: list[str] = []
    items: list[CheckItemIn] = []
    result: str = "open"
    inspector: str = ""
    notes: str = ""
    day: str = ""
    photo: str = ""


class IncidentIn(BaseModel):
    title: str
    severity: str = "low"
    description: str = ""
    actions: str = ""
    day: str = ""

    @field_validator("title")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _required_text(value)


class TsIn(BaseModel):
    day: str
    crew: str
    hours: float
    cost_kzt: int = 0
    notes: str = ""


class PersonIn(BaseModel):
    role: str
    name: str = ""


class DecisionIn(BaseModel):
    text: str
    owner_role: str
    due: str = ""


class MeetIn(BaseModel):
    title: str
    day: str
    attendees: str = ""
    decisions: str = ""
    actions: str = ""
    participants: list[PersonIn] = []
    agenda: str = ""
    decision_items: list[DecisionIn] = []

    @field_validator("title")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _required_text(value)


class PctIn(BaseModel):
    pct: int
    status: str | None = None


class TaskCreateIn(BaseModel):
    title: str
    start: str
    finish: str
    pct: int = 0
    status: str = "not_started"
    depends: str = ""

    @field_validator("title")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _required_text(value)


class TaskUpdateIn(BaseModel):
    title: str | None = None
    start: str | None = None
    finish: str | None = None
    pct: int | None = None
    status: str | None = None
    depends: str | None = None


class CoIn(BaseModel):
    title: str
    amount_kzt: int
    reason: str = ""

    @field_validator("title")
    @classmethod
    def _filled(cls, value: str) -> str:
        return _required_text(value)


def _project_or_404(pid: str) -> Project:
    project = store.get_project(pid)
    if not project:
        raise HTTPException(404, "Проект не найден")
    return project


def _guard(user: User, project: Project) -> Project:
    if not store.can_access_project(user, project):
        raise HTTPException(403, "Недостаточно прав")
    return project


def _guard_pid(user: User, pid: str) -> Project:
    return _guard(user, _project_or_404(pid))


def _owned_log(user: User, log_id: str):
    log = store.daily_logs.get(log_id)
    if not log:
        raise HTTPException(404, "Запись не найдена")
    project = store.get_project(log.project_id)
    if not project or not store.can_access_project(user, project):
        raise HTTPException(403, "Недостаточно прав")
    return log, project


def _saved(user: User, key: str | None, body: BaseModel, create):
    try:
        data = run_idempotent(user.id, key, body.model_dump_json(), create)
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот запрос уже отправлен с другими данными") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "data": data}


def _guard_item(user: User, table: dict, item_id: str) -> None:
    item = table.get(item_id)
    if not item:
        raise HTTPException(404, "Не найдено")
    project = store.get_project(getattr(item, "project_id", ""))
    if not project or not store.can_access_project(user, project):
        raise HTTPException(403, "Недостаточно прав")


@router.get("/projects")
def list_projects(user: User = Depends(require_user)):
    snaps = [store.project_snapshot(p.id) for p in store.projects_for(user)]
    return {"ok": True, "data": snaps}


@router.post("/projects")
def create_project(
    body: ProjectIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    def create():
        return store.create_project(user, body.title, body.address, body.deadline, body.budget_kzt)

    try:
        return _saved(user, idempotency_key, body, create)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/projects/{pid}")
def get_project(pid: str, user: User = Depends(require_user)):
    project = _guard_pid(user, pid)
    snap = store.project_snapshot(project.id)
    if not snap:
        raise HTTPException(404, "Проект не найден")
    return {"ok": True, "data": snap}


@router.get("/projects/{pid}/bundle")
def bundle(pid: str, user: User = Depends(require_user)):
    p = _member_or_404(user, pid)
    company_id = project_company_id(p)
    flags = flag_map(company_id)
    data = {
        "snapshot": store.project_snapshot(p.id, flags),
        "daily": [member_daily(item) for item in store._by_project(store.daily_logs, p.id)],
        "rfis": store._by_project(store.rfis, p.id),
        "submittals": store._by_project(store.submittals, p.id),
        "punches": store._by_project(store.punches, p.id),
        "inspections": store._by_project(store.inspections, p.id),
        "incidents": store._by_project(store.incidents, p.id),
        "drawings": store._by_project(store.drawings, p.id),
        "schedule": store._by_project(store.schedule, p.id),
        "budget": store._by_project(store.budget_lines, p.id),
        "changes": store._by_project(store.change_orders, p.id),
        "timesheets": store._by_project(store.timesheets, p.id),
        "meetings": store._by_project(store.meetings, p.id),
        "plan_meetings": [],
        "action_items": [],
        "task_assignees": [],
        "directory": store._by_project(store.directory, p.id),
        "members": store.list_project_members(p),
        "can_manage_members": store.can_manage_project(user, p),
        "can_approve_changes": store.is_assigned_supervisor(user, p),
    }
    from app.meetings import project_bundle

    plans, items, people = project_bundle(p)
    data["plan_meetings"] = plans
    data["action_items"] = items
    data["task_assignees"] = people
    return {"ok": True, "data": apply_bundle_flags(p, data, flags)}


def _member_or_404(user: User, pid: str) -> Project:
    project = _project_or_404(pid)
    if not store.can_access_project(user, project):
        raise HTTPException(404, "Не найдено")
    return project


@router.get("/projects/{pid}/drawings")
def list_drawings(pid: str, user: User = Depends(require_feature("drawings"))):
    project = _member_or_404(user, pid)
    return {"ok": True, "data": store._by_project(store.drawings, project.id)}


@router.get("/projects/{pid}/submittals")
def list_submittals(pid: str, user: User = Depends(require_feature("submittals"))):
    project = _member_or_404(user, pid)
    return {"ok": True, "data": store._by_project(store.submittals, project.id)}


@router.get("/projects/{pid}/members")
def list_members(pid: str, user: User = Depends(require_user)):
    project = _guard_pid(user, pid)
    return {"ok": True, "data": store.list_project_members(project)}


@router.post("/projects/{pid}/members")
def add_member(
    pid: str,
    body: MemberIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _project_or_404(pid)

    def create():
        return store.add_project_member(user, pid, body.email, body.role)

    try:
        return _saved(user, idempotency_key, body, create)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/projects/{pid}/members/{user_id}")
def remove_member(pid: str, user_id: str, user: User = Depends(require_user)):
    try:
        return {"ok": True, "data": store.remove_project_member(user, pid, user_id)}
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/projects/{pid}/daily")
def add_daily(
    pid: str,
    body: DailyIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    if body.delay_hours > 0 and not body.delays.strip():
        raise HTTPException(400, "Укажите причину простоя")
    return _saved(
        user,
        idempotency_key,
        body,
        lambda: member_daily(store.add_daily(pid, body.model_dump(), user.id, user.role)),
    )


@router.post("/daily/{log_id}/photos")
async def add_daily_photos(
    log_id: str,
    user: User = Depends(require_user),
    files: list[UploadFile] = File(...),
):
    log, project = _owned_log(user, log_id)
    if not files:
        raise HTTPException(400, "Нужно фото")
    if len(log.photos) + len(files) > 10:
        raise HTTPException(400, "Не больше 10 фото")
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        raw = await upload.read()
        job_id = f"job-{uuid4().hex[:12]}"
        create_job(job_id=job_id, owner_id=user.id, project_id=project.id, daily_log_id=log.id)
        payloads.append((job_id, raw))
    loop = asyncio.get_running_loop()
    processed = []
    for job_id, raw in payloads:
        future = loop.run_in_executor(PHOTO_POOL, process_in_pool, raw, job_id)
        try:
            item = await asyncio.wait_for(future, timeout=photo_timeout())
        except TimeoutError as exc:
            mark(job_id, "timeout", error="Превышено время обработки фото")
            raise HTTPException(408, "Обработка фото не успела завершиться") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        mark(
            job_id,
            "done",
            has_people=item.has_people,
            has_plates=item.has_plates,
            taken_at=item.taken_at,
            error="",
        )
        processed.append((job_id, item))
    added = []
    for job_id, item in processed:
        original_id = f"f-{uuid4().hex[:12]}"
        public_id = f"f-{uuid4().hex[:12]}"
        write_stored_file("original", f"{project.id}/{original_id}.jpg", item.original)
        write_stored_file("public", f"{project.id}/{public_id}.jpg", item.public)
        store.add_upload(
            user,
            f"{project.id}/{original_id}.jpg",
            item.content_type,
            project.id,
            kind="original",
            daily_log_id=log.id,
            file_id=original_id,
        )
        store.add_upload(
            user,
            f"{project.id}/{public_id}.jpg",
            "image/jpeg",
            project.id,
            kind="public",
            daily_log_id=log.id,
            file_id=public_id,
        )
        store.add_daily_photo(
            log.id,
            DailyPhoto(
                original_id=original_id,
                public_id=public_id,
                has_people=item.has_people,
                has_plates=item.has_plates,
                taken_at=item.taken_at,
            ),
        )
        added.append(
            {
                "job_id": job_id,
                "status": "done",
                "has_people": item.has_people,
                "has_plates": item.has_plates,
                "taken_at": item.taken_at,
            }
        )
    return {"ok": True, "data": {"log": member_daily(store.daily_logs[log.id]), "added": added}}


@router.get("/photos/jobs/{job_id}")
def photo_job(job_id: str, user: User = Depends(require_user)):
    row = get_job(job_id)
    if row is None or (row["owner_id"] != user.id and user.role != "admin"):
        raise HTTPException(404, "Задача не найдена")
    return {"ok": True, "data": row}


@router.post("/daily/{log_id}/voice")
async def add_daily_voice(
    log_id: str,
    user: User = Depends(require_user),
    file: UploadFile = File(...),
    duration_s: int = Form(0),
):
    log, project = _owned_log(user, log_id)
    if duration_s < 0 or duration_s > 120:
        raise HTTPException(400, "Голосовая заметка не длиннее 120 секунд")
    raw = await file.read()
    try:
        media_type, ext = _audio_file(raw, file.content_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    file_id = f"f-{uuid4().hex[:12]}"
    write_stored_file("voice", f"{project.id}/voice/{file_id}.{ext}", raw)
    store.add_upload(
        user,
        f"{project.id}/voice/{file_id}.{ext}",
        media_type,
        project.id,
        kind="voice",
        daily_log_id=log.id,
        file_id=file_id,
    )
    try:
        store.add_daily_voice(
            log.id,
            VoiceNote(
                file_id=file_id,
                duration_s=duration_s,
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                content_type=media_type,
            ),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "data": member_daily(store.daily_logs[log.id])}


@router.post("/daily/{log_id}/share")
def share_daily(log_id: str, body: ShareIn | None = None, user: User = Depends(require_user)):
    log, _project = _owned_log(user, log_id)
    days = body.expires_in_days if body else DEFAULT_SHARE_DAYS
    if share_is_active(log):
        return {
            "ok": True,
            "data": {"token": None, "expires_at": log.share_expires_at, "active": True},
        }
    token = new_share_token()
    expires = datetime.now(UTC) + timedelta(days=days)
    stored = store.set_daily_share(log.id, token_hash(token), expires.isoformat(timespec="seconds"))
    return {
        "ok": True,
        "data": {"token": token, "expires_at": stored.share_expires_at, "active": True},
    }


@router.delete("/daily/{log_id}/share")
def revoke_share(log_id: str, user: User = Depends(require_user)):
    log, _project = _owned_log(user, log_id)
    store.revoke_daily_share(log.id)
    return {"ok": True, "data": {"active": False}}


@router.post("/projects/{pid}/rfis")
def add_rfi(
    pid: str,
    body: RfiIn,
    user: User = Depends(require_feature("rfi")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    return _saved(user, idempotency_key, body, lambda: store.add_rfi(pid, body.model_dump()))


@router.post("/rfis/{rid}/answer")
def answer_rfi(rid: str, body: AnswerIn, user: User = Depends(require_feature("rfi"))):
    _guard_item(user, store.rfis, rid)
    try:
        return {"ok": True, "data": store.answer_rfi(rid, body.answer)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/punches")
def add_punch(
    pid: str,
    body: PunchIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    project = _guard_pid(user, pid)
    if body.photo.strip() and not feature_open_for_company(project_company_id(project), "punch_photos"):
        raise HTTPException(404, "Не найдено")
    return _saved(user, idempotency_key, body, lambda: store.add_punch(pid, body.model_dump()))


@router.post("/punches/{iid}/status")
def punch_status(iid: str, body: StatusIn, user: User = Depends(require_user)):
    _guard_item(user, store.punches, iid)
    try:
        return {"ok": True, "data": store.set_punch(iid, body.status)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/inspections")
def add_insp(
    pid: str,
    body: InspIn,
    user: User = Depends(require_feature("checklists")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    payload = body.model_dump()
    if not str(payload.get("inspector") or "").strip():
        payload["inspector"] = user.full_name
    return _saved(user, idempotency_key, body, lambda: store.add_inspection(pid, payload))


@router.post("/projects/{pid}/incidents")
def add_inc(
    pid: str,
    body: IncidentIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    return _saved(user, idempotency_key, body, lambda: store.add_incident(pid, body.model_dump()))


@router.post("/incidents/{iid}/close")
def close_inc(iid: str, user: User = Depends(require_user)):
    _guard_item(user, store.incidents, iid)
    try:
        return {"ok": True, "data": store.close_incident(iid)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/timesheets")
def add_ts(
    pid: str,
    body: TsIn,
    user: User = Depends(require_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    return _saved(user, idempotency_key, body, lambda: store.add_timesheet(pid, body.model_dump()))


@router.post("/projects/{pid}/meetings")
def add_mt(
    pid: str,
    body: MeetIn,
    user: User = Depends(require_feature("meetings")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    return _saved(user, idempotency_key, body, lambda: store.add_meeting(pid, body.model_dump()))


@router.post("/schedule/{tid}/progress")
def task_pct(tid: str, body: PctIn, user: User = Depends(require_feature("gantt"))):
    _guard_item(user, store.schedule, tid)
    try:
        return {"ok": True, "data": store.set_task_pct(tid, body.pct, body.status)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/schedule")
def add_task(
    pid: str,
    body: TaskCreateIn,
    user: User = Depends(require_feature("gantt")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    return _saved(user, idempotency_key, body, lambda: store.add_schedule_task(pid, body.model_dump()))


@router.post("/schedule/{tid}/update")
def update_task(tid: str, body: TaskUpdateIn, user: User = Depends(require_feature("gantt"))):
    _guard_item(user, store.schedule, tid)
    try:
        return {"ok": True, "data": store.update_schedule_task(tid, body.model_dump(exclude_unset=True))}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/schedule/{tid}/delete")
def delete_task(tid: str, user: User = Depends(require_feature("gantt"))):
    _guard_item(user, store.schedule, tid)
    try:
        store.delete_schedule_task(tid)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/changes")
def add_co(
    pid: str,
    body: CoIn,
    user: User = Depends(require_feature("changes")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _guard_pid(user, pid)
    return _saved(user, idempotency_key, body, lambda: store.add_change(pid, body.model_dump()))


@router.post("/changes/{cid}/status")
def co_status(cid: str, body: StatusIn, user: User = Depends(require_feature("changes"))):
    _guard_item(user, store.change_orders, cid)
    if body.status not in {"draft", "submitted", "approved", "rejected"}:
        raise HTTPException(400, "Неизвестный статус")
    item = store.change_orders[cid]
    project = store.get_project(item.project_id)
    if body.status in {"approved", "rejected"} and (not project or not store.is_assigned_supervisor(user, project)):
        raise HTTPException(403, "Утверждает только технадзор этого объекта")
    try:
        return {"ok": True, "data": store.set_change(cid, body.status)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
