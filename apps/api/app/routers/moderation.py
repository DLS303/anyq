from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_roles
from app.schemas import User, VerificationCreate
from app.sql_backend import page_body
from app.store import store

router = APIRouter(prefix="/v1/moderation", tags=["moderation"])


@router.get("/queue")
def queue(
    user: User = Depends(require_roles("moderator", "admin")),
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _ = user
    if limit is None:
        return {"ok": True, "data": [], "total": 0}
    return page_body([], 0, limit, offset)


@router.post("/verifications")
def grant_verification(body: VerificationCreate, user: User = Depends(require_roles("moderator", "admin"))):
    try:
        record = store.grant_verification(user, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "data": record}
