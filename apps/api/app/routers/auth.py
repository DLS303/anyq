from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_user
from app.schemas import LoginBody, RegisterBody, User
from app.store import store

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterBody):
    try:
        user, token = store.register(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": {"user": user, "token": token}}


@router.post("/login")
def login(body: LoginBody):
    try:
        user, token = store.login(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"ok": True, "data": {"user": user, "token": token}}


@router.get("/me")
def me(user: User = Depends(require_user)):
    return {"ok": True, "data": user}


@router.get("/users")
def demo_users():
    public = [
        {"email": u.email, "full_name": u.full_name, "role": u.role}
        for u in store.users_by_id.values()
        if u.email.endswith("@demo.superapp")
    ]
    return {"ok": True, "data": public, "demo_password": "demo123"}
