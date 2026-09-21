from fastapi import APIRouter, Depends, HTTPException, Query

from app.calc import development_estimate
from app.deps import current_user
from app.schemas import InquiryCreate, User
from app.store import store

router = APIRouter(prefix="/v1", tags=["marketplace"])


@router.get("/plots")
def list_plots(
    q: str | None = None,
    purpose: str | None = None,
    district: str | None = None,
    gas: str | None = None,
    electricity: str | None = None,
    water: str | None = None,
    verified: bool | None = Query(default=None),
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
):
    items = store.list_plots(
        q=q,
        purpose=purpose,
        district=district,
        gas=gas,
        electricity=electricity,
        water=water,
        verified=verified,
        status="published",
        lat=lat,
        lng=lng,
        radius_km=radius_km,
    )
    return {"ok": True, "data": items, "total": len(items)}


@router.get("/plots/suggest")
def suggest(q: str = ""):
    return {"ok": True, "data": store.suggest(q)}


@router.get("/plots/{plot_id}")
def get_plot(plot_id: str, user: User | None = Depends(current_user)):
    plot = store.get_plot(plot_id)
    if not plot:
        raise HTTPException(status_code=404, detail="Участок не найден")
    public = plot.status in ("published", "reserved")
    privileged = user and (user.role in ("moderator", "admin") or user.id == plot.owner_id)
    if not public and not privileged:
        raise HTTPException(status_code=404, detail="Участок не опубликован")
    fav = bool(user and store.is_favorite(user.id, plot.id))
    return {"ok": True, "data": plot, "calc": development_estimate(plot), "favorite": fav}


@router.post("/plots/{plot_id}/inquiries")
def create_inquiry(
    plot_id: str,
    body: InquiryCreate,
    user: User | None = Depends(current_user),
):
    plot = store.get_plot(plot_id)
    if not plot or plot.status != "published":
        raise HTTPException(status_code=404, detail="Участок не найден")
    if len(body.name.strip()) < 2 or len(body.phone.strip()) < 6:
        raise HTTPException(status_code=400, detail="Укажите имя и телефон")
    item = store.add_inquiry(plot, body, user.id if user else None)
    return {"ok": True, "data": item}
