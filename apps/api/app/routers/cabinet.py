from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.deps import require_user
from app.schemas import PlotCreate, SavedSearchCreate, User
from app.store import store

router = APIRouter(prefix="/v1/cabinet", tags=["cabinet"])
UPLOADS = Path(__file__).resolve().parents[3] / "data" / "uploads"
ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/me")
def me(user: User = Depends(require_user)):
    return {"ok": True, "data": user}


@router.get("/plots")
def my_plots(user: User = Depends(require_user)):
    if user.role in ("moderator", "admin"):
        items = list(store.plots.values())
    else:
        items = [p for p in store.plots.values() if p.owner_id == user.id]
    return {"ok": True, "data": items}


@router.post("/plots")
def publish_plot(body: PlotCreate, user: User = Depends(require_user)):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Публиковать может продавец")
    try:
        plot = store.create_plot(user, body)
    except ValueError as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": plot}


@router.patch("/plots/{plot_id}")
def edit_plot(plot_id: str, body: PlotCreate, user: User = Depends(require_user)):
    try:
        plot = store.update_plot(plot_id, user, body)
    except (ValueError, PermissionError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": plot}


@router.post("/plots/{plot_id}/submit")
def resubmit(plot_id: str, user: User = Depends(require_user)):
    try:
        plot = store.submit_plot(plot_id, user)
    except (ValueError, PermissionError) as exc:
        raise _http(exc) from exc
    return {"ok": True, "data": plot}


@router.post("/photos")
async def upload_photo(user: User = Depends(require_user), file: UploadFile = File(...)):
    _ = user
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status_code=400, detail="Только jpg, png, webp")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл больше 8 МБ")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}{suffix}"
    (UPLOADS / name).write_bytes(raw)
    return {"ok": True, "data": {"url": f"/uploads/{name}"}}


@router.get("/inquiries")
def my_inquiries(user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_inquiries(user)}


@router.post("/inquiries/{inquiry_id}")
def inquiry_status(inquiry_id: str, status: str = "seen", user: User = Depends(require_user)):
    try:
        item = store.set_inquiry_status(user, inquiry_id, status)
    except PermissionError as exc:
        raise _http(exc) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return {"ok": True, "data": item}


@router.get("/favorites")
def my_favorites(user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_favorites(user.id)}


@router.post("/favorites/{plot_id}")
def toggle_favorite(plot_id: str, user: User = Depends(require_user)):
    plot = store.get_plot(plot_id)
    if not plot:
        raise HTTPException(status_code=404, detail="Участок не найден")
    on = store.toggle_favorite(user.id, plot.id)
    return {"ok": True, "data": {"favorite": on, "plot_id": plot.id}}


@router.get("/searches")
def my_searches(user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_searches(user.id)}


@router.post("/searches")
def save_search(body: SavedSearchCreate, user: User = Depends(require_user)):
    item = store.save_search(user, body.title, body.params)
    return {"ok": True, "data": item}


@router.delete("/searches/{search_id}")
def delete_search(search_id: str, user: User = Depends(require_user)):
    if not store.delete_search(user.id, search_id):
        raise HTTPException(status_code=404, detail="Поиск не найден")
    return {"ok": True, "data": True}
