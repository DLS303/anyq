from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_user
from app.schemas import (
    FUNNEL_STAGES,
    CrmActivityCreate,
    CrmActivityToggle,
    CrmContactCreate,
    CrmInvoiceCreate,
    DealCreate,
    DealMove,
    DealToProject,
    LeadConvert,
    LeadCreate,
    User,
)
from app.sql_backend import page_body
from app.store import store

router = APIRouter(prefix="/v1/crm", tags=["crm"])


def _call(fn):
    try:
        return fn()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/funnels")
def funnels():
    return {"ok": True, "data": FUNNEL_STAGES}


@router.get("/deals")
def deals(
    funnel: str | None = None,
    q: str | None = None,
    user: User = Depends(require_user),
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if limit is None and not q:
        items = store.list_deals(user, funnel)
        return {"ok": True, "data": items, "total": len(items)}
    if limit is None:
        items = store.list_deals(user, funnel)
        needle = q.lower()
        items = [
            deal
            for deal in items
            if needle in deal.title.lower()
            or needle in (deal.client_name or "").lower()
            or needle in (deal.client_phone or "")
            or needle in (deal.plot_title or "").lower()
        ]
        return {"ok": True, "data": items, "total": len(items)}
    items, total = store.page_deals(user, limit=limit, offset=offset, funnel=funnel, q=q)
    return page_body(items, total, limit, offset)


@router.post("/deals")
def create_deal(body: DealCreate, user: User = Depends(require_user)):
    deal = store.create_deal(user, body)
    return {"ok": True, "data": deal}


@router.get("/deals/{deal_id}")
def get_deal(deal_id: str, user: User = Depends(require_user)):
    deal = _call(lambda: store.require_deal(user, deal_id))
    activities = store.list_crm_activities(user, deal_id=deal_id)
    invoices = [store.invoice_payload(user, item) for item in store.list_crm_invoices(user, deal_id=deal_id)]
    return {"ok": True, "data": deal, "activities": activities, "invoices": invoices}


@router.post("/deals/{deal_id}/move")
def move(deal_id: str, body: DealMove, user: User = Depends(require_user)):
    deal = _call(lambda: store.move_deal(user, deal_id, body))
    return {"ok": True, "data": deal}


@router.post("/deals/{deal_id}/to-project")
def to_project(deal_id: str, body: DealToProject | None = None, user: User = Depends(require_user)):
    payload = body or DealToProject()
    project = _call(
        lambda: store.deal_to_project(user, deal_id, payload.address, payload.finish, payload.budget_kzt)
    )
    return {"ok": True, "data": project}


@router.get("/leads")
def leads(status: str | None = None, user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_leads(user, status)}


@router.post("/leads")
def create_lead(body: LeadCreate, user: User = Depends(require_user)):
    lead = store.create_lead(user, body)
    return {"ok": True, "data": lead}


@router.post("/leads/{lead_id}/convert")
def convert_lead(lead_id: str, body: LeadConvert, user: User = Depends(require_user)):
    deal = _call(lambda: store.convert_lead(user, lead_id, body))
    return {"ok": True, "data": deal}


@router.get("/contacts")
def contacts(
    q: str | None = None,
    ctype: str | None = None,
    user: User = Depends(require_user),
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if limit is None:
        items = store.list_crm_contacts(user, q, ctype)
        return {"ok": True, "data": items, "total": len(items)}
    items, total = store.page_contacts(user, limit=limit, offset=offset, q=q, ctype=ctype)
    return page_body(items, total, limit, offset)


@router.post("/contacts")
def create_contact(body: CrmContactCreate, user: User = Depends(require_user)):
    contact = store.create_crm_contact(user, body)
    return {"ok": True, "data": contact}


@router.get("/activities")
def activities(deal_id: str | None = None, lead_id: str | None = None, user: User = Depends(require_user)):
    rows = _call(lambda: store.list_crm_activities(user, deal_id, lead_id))
    return {"ok": True, "data": rows}


@router.post("/activities")
def create_activity(body: CrmActivityCreate, user: User = Depends(require_user)):
    act = _call(lambda: store.create_crm_activity(user, body))
    return {"ok": True, "data": act}


@router.post("/activities/{activity_id}/toggle")
def toggle_activity(activity_id: str, body: CrmActivityToggle, user: User = Depends(require_user)):
    act = _call(lambda: store.toggle_crm_activity(user, activity_id, body.completed))
    return {"ok": True, "data": act}


@router.get("/invoices")
def invoices(deal_id: str | None = None, user: User = Depends(require_user)):
    rows = _call(lambda: store.list_crm_invoices(user, deal_id))
    return {"ok": True, "data": [store.invoice_payload(user, item) for item in rows]}


@router.post("/invoices")
def create_invoice(body: CrmInvoiceCreate, user: User = Depends(require_user)):
    inv = _call(lambda: store.create_crm_invoice(user, body))
    return {"ok": True, "data": store.invoice_payload(user, inv)}


@router.post("/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: str, user: User = Depends(require_user)):
    inv = _call(lambda: store.pay_crm_invoice(user, invoice_id))
    return {"ok": True, "data": store.invoice_payload(user, inv)}


@router.get("/analytics")
def analytics(user: User = Depends(require_user)):
    return {"ok": True, "data": store.crm_analytics(user)}
