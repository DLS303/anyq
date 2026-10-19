from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_user
from app.schemas import OrderCreate, OrderStatusUpdate, ReviewCreate, User
from app.store import store

router = APIRouter(prefix="/v1", tags=["specialists"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/specialists")
def list_specialists(category: str | None = None, q: str | None = None):
    return {"ok": True, "data": store.list_specialists(category=category, q=q)}


@router.get("/specialists/{sid}")
def get_specialist(sid: str):
    spec = store.get_specialist(sid)
    if not spec:
        raise HTTPException(status_code=404, detail="Специалист не найден")
    return {
        "ok": True,
        "data": store.specialist_public(spec),
        "reviews": [r.model_dump() for r in store.list_reviews(spec.id)],
    }


@router.post("/specialists/{sid}/orders")
def order_specialist(sid: str, body: OrderCreate, user: User = Depends(require_user)):
    body.specialist_id = sid
    try:
        order = store.create_order(user, body)
    except ValueError as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": order}


@router.get("/orders")
def my_orders(user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_orders(user)}


@router.post("/orders/{oid}/status")
def order_status(oid: str, body: OrderStatusUpdate, user: User = Depends(require_user)):
    try:
        order = store.set_order_status(
            user,
            oid,
            body.status,
            body.quote_kzt,
            body.quote_term,
            body.quote_comment,
        )
    except (ValueError, PermissionError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": order}


@router.post("/orders/{oid}/review")
def review_order(oid: str, body: ReviewCreate, user: User = Depends(require_user)):
    try:
        item = store.add_review(user, oid, body)
    except (ValueError, PermissionError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": item}
