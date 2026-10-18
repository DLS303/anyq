from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_user
from app.schemas import User
from app.site_models import Project
from app.store import store

router = APIRouter(prefix="/v1/site", tags=["site"])


class DailyIn(BaseModel):
    day: str
    weather: str = "clear"
    temp_c: int = 20
    workers: int = 0
    notes: str = ""
    delays: str = ""


class RfiIn(BaseModel):
    title: str
    question: str
    drawing: str = ""
    assignee_id: str | None = None


class AnswerIn(BaseModel):
    answer: str


class PunchIn(BaseModel):
    title: str
    location: str = ""
    trade: str = ""
    photo: str = ""


class StatusIn(BaseModel):
    status: str


class InspIn(BaseModel):
    title: str
    checklist: list[str] = []
    result: str = "open"
    inspector: str = ""
    notes: str = ""
    day: str = ""


class IncidentIn(BaseModel):
    title: str
    severity: str = "low"
    description: str = ""
    actions: str = ""
    day: str = ""


class TsIn(BaseModel):
    day: str
    crew: str
    hours: float
    cost_kzt: int = 0
    notes: str = ""


class MeetIn(BaseModel):
    title: str
    day: str
    attendees: str = ""
    decisions: str = ""
    actions: str = ""


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


def _guard_item(user: User, table: dict, item_id: str) -> None:
    item = table.get(item_id)
    if not item:
        raise HTTPException(404, "Не найдено")
    project = store.get_project(getattr(item, "project_id", ""))
    if not project or not store.can_access_project(user, project):
        raise HTTPException(403, "Недостаточно прав")


@router.get("/projects")
def list_projects(user: User = Depends(require_user)):
    visible = [p for p in store.list_projects() if store.can_access_project(user, p)]
    snaps = [store.project_snapshot(p.id) for p in visible]
    return {"ok": True, "data": snaps}


@router.get("/projects/{pid}")
def get_project(pid: str, user: User = Depends(require_user)):
    project = _guard_pid(user, pid)
    snap = store.project_snapshot(project.id)
    if not snap:
        raise HTTPException(404, "Проект не найден")
    return {"ok": True, "data": snap}


@router.get("/projects/{pid}/bundle")
def bundle(pid: str, user: User = Depends(require_user)):
    p = _guard_pid(user, pid)
    return {
        "ok": True,
        "data": {
            "snapshot": store.project_snapshot(p.id),
            "daily": store._by_project(store.daily_logs, p.id),
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
            "directory": store._by_project(store.directory, p.id),
        },
    }


@router.post("/projects/{pid}/daily")
def add_daily(pid: str, body: DailyIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_daily(pid, body.model_dump(), user.id)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/rfis")
def add_rfi(pid: str, body: RfiIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_rfi(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/rfis/{rid}/answer")
def answer_rfi(rid: str, body: AnswerIn, user: User = Depends(require_user)):
    _guard_item(user, store.rfis, rid)
    try:
        return {"ok": True, "data": store.answer_rfi(rid, body.answer)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/punches")
def add_punch(pid: str, body: PunchIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_punch(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/punches/{iid}/status")
def punch_status(iid: str, body: StatusIn, user: User = Depends(require_user)):
    _guard_item(user, store.punches, iid)
    try:
        return {"ok": True, "data": store.set_punch(iid, body.status)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/inspections")
def add_insp(pid: str, body: InspIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_inspection(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/incidents")
def add_inc(pid: str, body: IncidentIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_incident(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/incidents/{iid}/close")
def close_inc(iid: str, user: User = Depends(require_user)):
    _guard_item(user, store.incidents, iid)
    try:
        return {"ok": True, "data": store.close_incident(iid)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/timesheets")
def add_ts(pid: str, body: TsIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_timesheet(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/meetings")
def add_mt(pid: str, body: MeetIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_meeting(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/schedule/{tid}/progress")
def task_pct(tid: str, body: PctIn, user: User = Depends(require_user)):
    _guard_item(user, store.schedule, tid)
    try:
        return {"ok": True, "data": store.set_task_pct(tid, body.pct, body.status)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/schedule")
def add_task(pid: str, body: TaskCreateIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_schedule_task(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/schedule/{tid}/update")
def update_task(tid: str, body: TaskUpdateIn, user: User = Depends(require_user)):
    _guard_item(user, store.schedule, tid)
    try:
        return {"ok": True, "data": store.update_schedule_task(tid, body.model_dump(exclude_unset=True))}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/schedule/{tid}/delete")
def delete_task(tid: str, user: User = Depends(require_user)):
    _guard_item(user, store.schedule, tid)
    try:
        store.delete_schedule_task(tid)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{pid}/changes")
def add_co(pid: str, body: CoIn, user: User = Depends(require_user)):
    _guard_pid(user, pid)
    try:
        return {"ok": True, "data": store.add_change(pid, body.model_dump())}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/changes/{cid}/status")
def co_status(cid: str, body: StatusIn, user: User = Depends(require_user)):
    _guard_item(user, store.change_orders, cid)
    try:
        return {"ok": True, "data": store.set_change(cid, body.status)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
