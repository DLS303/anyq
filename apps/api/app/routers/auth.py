from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import require_roles, require_user
from app.schemas import LoginBody, RegisterBody, User
from app.store import ConsentRequired, store

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _client_meta(request: Request) -> tuple[str, str]:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
    return ip, request.headers.get("user-agent", "")


@router.post("/register")
def register(body: RegisterBody, request: Request):
    ip, ua = _client_meta(request)
    try:
        user, token = store.register(body, ip=ip, user_agent=ua)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": {"user": user, "token": token}}


@router.post("/login")
def login(body: LoginBody, request: Request):
    ip, ua = _client_meta(request)
    try:
        user, token = store.login(
            body.email,
            body.password,
            consent=body.consent_offer_pd,
            ip=ip,
            user_agent=ua,
        )
    except ConsentRequired as exc:
        raise HTTPException(status_code=428, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"ok": True, "data": {"user": user, "token": token}}


@router.get("/me")
def me(user: User = Depends(require_user)):
    return {"ok": True, "data": user}


@router.get("/consents")
def my_consents(user: User = Depends(require_user)):
    return {"ok": True, "data": store.consents_for(user.id)}


@router.get("/users")
def list_demo_users(user: User = Depends(require_roles("admin"))):
    _ = user
    public = [
        {"email": u.email, "full_name": u.full_name, "role": u.role}
        for u in store.users_by_id.values()
        if u.email.endswith("@demo.superapp")
    ]
    return {"ok": True, "data": public}
