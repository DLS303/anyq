"""Public storefront, supplier catalog, and the request-to-offer flow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.deps import current_user, require_user
from app.marketplace_service import (
    CATEGORIES,
    MarketError,
    accept_deal,
    assigned,
    cities,
    comparison,
    contact_supplier,
    create_request,
    create_review,
    hide_item,
    home,
    import_prices,
    list_own,
    my_rating,
    repeat_request,
    reply_review,
    request_view,
    save_item,
    search_catalog,
    select_offer,
    submit_offer,
    supplier_public,
    update_review,
)
from app.schemas import User
from app.store import store

router = APIRouter(prefix="/v1/market", tags=["market"])


class LineIn(BaseModel):
    catalog_id: str | None = None
    request_line_id: str | None = None
    name: str = ""
    unit: str = ""
    qty: float = 1
    category: str = ""
    price_tiyn: int | None = None
    vat_included: bool | None = None
    vat_rate: int | None = None
    lead_days: int = 0
    analog: bool = False
    source: str = ""


class RequestIn(BaseModel):
    title: str = "Заявка на материалы"
    project_id: str | None = None
    supplier_ids: list[str] = Field(default_factory=list)
    lines: list[LineIn]


class ItemIn(BaseModel):
    name: str
    category: str
    unit: str
    price_tiyn: int
    source: str
    vat_included: bool | None = None
    vat_rate: int | None = None
    brand: str = ""
    sku: str = ""
    city: str = ""
    stock: str = "in_stock"
    lead_days: int = 0
    price_date: str = ""
    valid_days: int = 7
    hidden: bool = False
    source_kind: str = "file"


class HideIn(BaseModel):
    hidden: bool = True


class OfferIn(BaseModel):
    request_id: str
    source: str
    lines: list[LineIn]


class ReviewIn(BaseModel):
    quality: int = Field(ge=1, le=5)
    delivery: int = Field(ge=1, le=5)
    price: int = Field(ge=1, le=5)
    communication: int = Field(ge=1, le=5)
    comment: str = ""


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=280)


class AcceptIn(BaseModel):
    delivered_at: str = ""
    on_time: bool | None = None
    price_matched: bool = True
    acceptance_ok: bool = True
    esf_ok: bool | None = None
    invoice_source_id: str = ""
    invoice_price_tiyn: int | None = None


def _run(fn):
    session = store._sql.factory()
    try:
        with session.begin():
            data = fn(session)
        return {"ok": True, "data": data}
    except MarketError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    finally:
        session.close()


def _page(limit: int, offset: int, rows, total: int):
    return {"ok": True, "data": rows, "limit": limit, "offset": offset, "total": total}


@router.get("/home")
def market_home():
    return {"ok": True, "data": home()}


@router.get("/cities")
def market_cities():
    session = store._sql.factory()
    try:
        return {"ok": True, "data": cities(session)}
    finally:
        session.close()


@router.get("/catalog")
def market_catalog(
    q: str = "",
    category: str = "",
    city: str = "",
    price_min: int | None = None,
    price_max: int | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if category and category not in CATEGORIES:
        raise HTTPException(400, "Выберите категорию")
    session = store._sql.factory()
    try:
        rows, total = search_catalog(session, q, category, city, price_min, price_max, limit, offset)
    finally:
        session.close()
    return _page(limit, offset, rows, total)


@router.get("/suppliers/{company_id}")
def market_supplier(
    company_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    session = store._sql.factory()
    try:
        try:
            data = supplier_public(session, company_id, limit, offset)
        except MarketError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
    finally:
        session.close()
    return {"ok": True, "data": data}


@router.post("/suppliers/{company_id}/contact")
def market_contact(company_id: str, user: User = Depends(require_user)):
    return _run(lambda session: contact_supplier(session, user, company_id))


@router.get("/my/items")
def market_my_items(user: User = Depends(require_user)):
    return _run(lambda session: list_own(session, user))


@router.post("/my/items")
def market_add_item(body: ItemIn, user: User = Depends(require_user)):
    return _run(lambda session: save_item(session, user, body.model_dump()))


@router.patch("/my/items/{item_id}")
def market_edit_item(item_id: str, body: ItemIn, user: User = Depends(require_user)):
    return _run(lambda session: save_item(session, user, body.model_dump(), item_id))


@router.post("/my/items/{item_id}/hide")
def market_hide_item(item_id: str, body: HideIn, user: User = Depends(require_user)):
    return _run(lambda session: hide_item(session, user, item_id, body.hidden))


@router.post("/my/import")
async def market_import(
    file: UploadFile = File(...),
    user: User = Depends(require_user),
):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "Файл больше 5 МБ")
    return _run(lambda session: import_prices(session, user, raw, file.filename or "prices.csv"))


@router.get("/my/rating")
def market_my_rating(user: User = Depends(require_user)):
    return _run(lambda session: my_rating(session, user))


@router.get("/assigned")
def market_assigned(user: User = Depends(require_user)):
    # TODO(registration): the supplier inbox reads this same recipient list.
    return _run(lambda session: assigned(session, user))


@router.post("/requests")
def market_create_request(body: RequestIn, user: User = Depends(require_user)):
    return _run(lambda session: create_request(session, user, body.model_dump()))


@router.post("/requests/{request_id}/repeat")
def market_repeat(request_id: str, user: User = Depends(require_user)):
    return _run(lambda session: repeat_request(session, user, request_id))


@router.get("/requests/{request_id}")
def market_request(request_id: str, user: User = Depends(require_user)):
    return _run(lambda session: comparison(session, user, request_id))


@router.post("/offers")
def market_offer(body: OfferIn, user: User = Depends(require_user)):
    return _run(lambda session: submit_offer(session, user, body.model_dump()))


@router.post("/offers/{offer_id}/select")
def market_select(offer_id: str, user: User = Depends(require_user)):
    return _run(lambda session: select_offer(session, user, offer_id))


@router.post("/deals/{deal_id}/accept")
def market_accept(deal_id: str, body: AcceptIn, user: User = Depends(require_user)):
    payload = body.model_dump()
    if payload.get("on_time") is None:
        payload.pop("on_time")
    return _run(lambda session: accept_deal(session, user, deal_id, payload))


@router.post("/deals/{deal_id}/reviews")
def market_review(deal_id: str, body: ReviewIn, user: User = Depends(require_user)):
    return _run(lambda session: create_review(session, user, deal_id, body.model_dump()))


@router.patch("/reviews/{review_id}")
def market_review_edit(review_id: str, body: ReviewIn, user: User = Depends(require_user)):
    return _run(lambda session: update_review(session, user, review_id, body.model_dump()))


@router.post("/reviews/{review_id}/reply")
def market_review_reply(review_id: str, body: ReplyIn, user: User = Depends(require_user)):
    return _run(lambda session: reply_review(session, user, review_id, body.text))


@router.get("/whoami")
def market_who(user: User | None = Depends(current_user)):
    if user is None:
        return {"ok": True, "data": None}
    return {"ok": True, "data": {"id": user.id, "role": user.role, "name": user.full_name}}
