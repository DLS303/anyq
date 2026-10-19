from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_roles
from app.schemas import ModerateBody, User, VerificationCreate
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
        items = store.queue()
        return {"ok": True, "data": items, "total": len(items)}
    items, total = store.page_queue(limit=limit, offset=offset)
    return page_body(items, total, limit, offset)


@router.post("/verifications")
def grant_verification(body: VerificationCreate, user: User = Depends(require_roles("moderator", "admin"))):
    try:
        record = store.grant_verification(user, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "data": record}


@router.post("/{plot_id}")
def moderate(
    plot_id: str,
    body: ModerateBody,
    user: User = Depends(require_roles("moderator", "admin")),
):
    _ = user
    plot = store.moderate(plot_id, body.action, body.comment)
    if not plot:
        raise HTTPException(status_code=404, detail="Участок не найден")
    return {"ok": True, "data": plot}
