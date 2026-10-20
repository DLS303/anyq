from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.deps import require_user
from app.invitations import (
    InvitationClosed,
    accept,
    create_invitation,
    list_invitations,
    preview,
    revoke,
)
from app.schemas import User

router = APIRouter(prefix="/v1", tags=["invitations"])


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str = Field(min_length=1, max_length=40)
    project_id: str | None = None


class AcceptIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: str
    password: str
    full_name: str
    phone: str
    consent_offer_pd: bool = False
    role: str | None = None


def _closed(exc: InvitationClosed) -> JSONResponse:
    return JSONResponse(status_code=410, content={"code": exc.code, "detail": str(exc)})


def _fail(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc) or "Недостаточно прав") from exc
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc) or "Не найдено") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise exc


def _client(request: Request) -> tuple[str, str]:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
    return ip, request.headers.get("user-agent", "")


@router.post("/invitations")
def create_company_invitation(body: InviteIn, user: User = Depends(require_user)):
    try:
        data = create_invitation(user, body.role.strip(), body.project_id)
    except (PermissionError, LookupError, ValueError) as exc:
        _fail(exc)
    return {"ok": True, "data": data}


@router.get("/invitations")
def company_invitations(project_id: str | None = None, user: User = Depends(require_user)):
    try:
        data = list_invitations(user, project_id)
    except (PermissionError, LookupError) as exc:
        _fail(exc)
    return {"ok": True, "data": data}


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(invitation_id: str, user: User = Depends(require_user)):
    try:
        data = revoke(user, invitation_id)
    except (PermissionError, LookupError, ValueError) as exc:
        _fail(exc)
    return {"ok": True, "data": data}


@router.get("/invitations/token/{token}")
def invitation_preview(token: str):
    try:
        data = preview(token)
    except LookupError as exc:
        _fail(exc)
    return {"ok": True, "data": data}


@router.post("/invitations/token/{token}/accept")
def invitation_accept(token: str, body: AcceptIn, request: Request):
    ip, user_agent = _client(request)
    try:
        user, auth = accept(token, body, ip=ip, user_agent=user_agent)
    except InvitationClosed as exc:
        return _closed(exc)
    except (PermissionError, LookupError, ValueError) as exc:
        _fail(exc)
    return {"ok": True, "data": {"user": user, "token": auth}}


@router.post("/site/projects/{project_id}/invitations")
def create_project_invitation(project_id: str, body: InviteIn, user: User = Depends(require_user)):
    try:
        data = create_invitation(user, body.role.strip(), project_id)
    except (PermissionError, LookupError, ValueError) as exc:
        _fail(exc)
    return {"ok": True, "data": data}


@router.get("/site/projects/{project_id}/invitations")
def project_invitations(project_id: str, user: User = Depends(require_user)):
    try:
        data = list_invitations(user, project_id)
    except (PermissionError, LookupError) as exc:
        _fail(exc)
    return {"ok": True, "data": data}
