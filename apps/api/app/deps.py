from fastapi import Header, HTTPException

from app.authutil import read_token
from app.schemas import User
from app.store import store


def current_user(
    authorization: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None),
) -> User | None:
    if authorization and authorization.lower().startswith("bearer "):
        uid = read_token(authorization.split(" ", 1)[1].strip())
        if uid:
            user = store.get_user(uid)
            if user:
                return user
    if x_demo_user:
        return store.get_user_by_email(x_demo_user)
    return None


def require_user(
    authorization: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None),
) -> User:
    user = current_user(authorization, x_demo_user)
    if not user:
        raise HTTPException(status_code=401, detail="Нужна авторизация")
    return user


def require_roles(*roles: str):
    def inner(
        authorization: str | None = Header(default=None),
        x_demo_user: str | None = Header(default=None),
    ) -> User:
        user = require_user(authorization, x_demo_user)
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user

    return inner
