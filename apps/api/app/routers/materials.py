from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_user
from app.schemas import MaterialCreate, MaterialOrderCreate, User
from app.store import store
from app.transitions import ConflictError

router = APIRouter(prefix="/v1", tags=["materials"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/materials")
def list_materials(category: str | None = None, q: str | None = None):
    return {"ok": True, "data": [store.material_public(item) for item in store.list_materials(category=category, q=q)]}


@router.get("/materials/{mid}")
def get_material(mid: str):
    item = store.get_material(mid)
    if not item:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    return {"ok": True, "data": store.material_public(item)}


@router.post("/materials")
def add_material(body: MaterialCreate, user: User = Depends(require_user)):
    try:
        item = store.create_material(user, body)
    except PermissionError as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": item}


@router.get("/cabinet/materials")
def my_materials(user: User = Depends(require_user)):
    if user.role == "admin":
        return {"ok": True, "data": [store.material_public(item) for item in store.materials.values()]}
    return {"ok": True, "data": [store.material_public(item) for item in store.supplier_materials(user.id)]}


@router.post("/material-orders")
def order_material(body: MaterialOrderCreate, user: User = Depends(require_user)):
    try:
        order = store.create_material_order(user, body)
    except ValueError as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": order}


@router.get("/material-orders")
def list_material_orders(user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_material_orders(user)}


@router.post("/material-orders/{oid}/status")
def material_order_status(oid: str, status: str = Query(...), user: User = Depends(require_user)):
    try:
        order = store.set_material_order_status(user, oid, status)
    except (ValueError, PermissionError, ConflictError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": order}
