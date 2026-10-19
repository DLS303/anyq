"""Meeting routes.

Ids are taken only from request.path_params. A query-string pid cannot open
another company's flag or project. The feature gate is 404 when the flag is off.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.company_features import require_feature
from app.deps import require_user
from app.idempotency import IdempotencyConflict, run_idempotent
from app.meetings import (
    Access,
    Conflict,
    access_action,
    access_meeting,
    access_project,
    create_plan,
    meeting_file,
    meeting_links,
    project_bundle,
    set_status,
    tasks_for_assignee,
    tombstone,
)
from app.schemas import User

router = APIRouter(prefix="/v1/site", tags=["meetings"])


class ItemIn(BaseModel):
    id: str | None = None
    text: str = ""
    assignee_id: str = ""
    due_date: str = ""
    source: Literal["meeting", "punch", "rfi"] = "meeting"
    source_id: str | None = None


class PlanIn(BaseModel):
    id: str | None = None
    title: str = ""
    day: str = ""
    agenda: str = ""
    participants: list[str] = Field(default_factory=list)
    action_items: list[ItemIn] = Field(default_factory=list)


class StatusIn(BaseModel):
    status: Literal["open", "done", "cancelled"]
    row_version: int


class VersionIn(BaseModel):
    row_version: int


def require_meetings(request: Request, user: User = Depends(require_user)) -> Access:
    """Feature and membership. Path ids only — never the query string."""
    path = request.path_params
    if "aid" in path:
        return access_action(str(path["aid"]), user)
    if "mid" in path:
        return access_meeting(str(path["mid"]), user)
    if "pid" in path:
        return access_project(str(path["pid"]), user)
    raise HTTPException(status_code=404, detail="Не найдено")


def _run(access: Access, key: str | None, body: BaseModel, create):
    try:
        data = run_idempotent(access.user.id, key, body.model_dump_json(), create)
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="Этот запрос уже отправлен с другими данными") from exc
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": data}


@router.post("/projects/{pid}/meeting-tasks")
def post_plan(
    body: PlanIn,
    access: Access = Depends(require_meetings),
    _user: User = Depends(require_feature("meetings")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _run(access, idempotency_key, body, lambda: create_plan(access, body.model_dump()))


@router.get("/projects/{pid}/action-items")
def list_items(
    access: Access = Depends(require_meetings),
    _user: User = Depends(require_feature("meetings")),
):
    _plans, items, _people = project_bundle(access.project)
    mine = tasks_for_assignee(access.user.id, "open", access.project.id)
    return {"ok": True, "data": {"action_items": items, "mine": mine}}


@router.get("/projects/{pid}/plan-meetings")
def list_plans(
    access: Access = Depends(require_meetings),
    _user: User = Depends(require_feature("meetings")),
):
    plans, items, people = project_bundle(access.project)
    return {"ok": True, "data": {"plan_meetings": plans, "action_items": items, "task_assignees": people}}


@router.post("/action-items/{aid}/status")
def post_status(body: StatusIn, access: Access = Depends(require_meetings)):
    try:
        data = set_status(access, body.status, body.row_version)
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    return {"ok": True, "data": data}


@router.post("/action-items/{aid}/delete")
def post_delete(body: VersionIn, access: Access = Depends(require_meetings)):
    try:
        data = tombstone(access, body.row_version)
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    return {"ok": True, "data": data}


@router.get("/meetings/{mid}/file")
def read_file(access: Access = Depends(require_meetings)):
    pdf = meeting_file(access)
    return Response(content=pdf, media_type="application/pdf")


@router.get("/meetings/{mid}/links")
def read_links(access: Access = Depends(require_meetings)):
    return {"ok": True, "data": meeting_links(access)}


@router.get("/meetings/{mid}")
def read_meeting(access: Access = Depends(require_meetings)):
    return {"ok": True, "data": access.meeting}
