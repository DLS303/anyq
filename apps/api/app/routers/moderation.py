from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_roles
from app.schemas import ModerateBody, User, VerificationCreate
from app.store import store

router = APIRouter(prefix="/v1/moderation", tags=["moderation"])


@router.get("/queue")
def queue(user: User = Depends(require_roles("moderator", "admin"))):
    _ = user
    return {"ok": True, "data": store.queue()}


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
