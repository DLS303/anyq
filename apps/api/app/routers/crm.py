from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_user
from app.schemas import (
    CrmActivityCreate,
    CrmActivityToggle,
    CrmContactCreate,
    CrmInvoiceCreate,
    DealCreate,
    DealMove,
    FUNNEL_STAGES,
    LeadConvert,
    LeadCreate,
    User,
)
from app.store import store

router = APIRouter(prefix="/v1/crm", tags=["crm"])


@router.get("/funnels")
def funnels():
    return {"ok": True, "data": FUNNEL_STAGES}


@router.get("/deals")
def deals(funnel: str | None = None, user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_deals(user, funnel)}


@router.post("/deals")
def create_deal(body: DealCreate, user: User = Depends(require_user)):
    deal = store.create_deal(user, body)
    return {"ok": True, "data": deal}


@router.get("/deals/{deal_id}")
def get_deal(deal_id: str, user: User = Depends(require_user)):
    deal = store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    activities = store.list_crm_activities(deal_id=deal_id)
    invoices = store.list_crm_invoices(deal_id=deal_id)
    return {"ok": True, "data": deal, "activities": activities, "invoices": invoices}


@router.post("/deals/{deal_id}/move")
def move(deal_id: str, body: DealMove, user: User = Depends(require_user)):
    try:
        deal = store.move_deal(user, deal_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "data": deal}


@router.post("/deals/{deal_id}/to-project")
def to_project(deal_id: str, user: User = Depends(require_user)):
    try:
        project = store.deal_to_project(user, deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": project}


@router.get("/leads")
def leads(status: str | None = None, user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_leads(user, status)}


@router.post("/leads")
def create_lead(body: LeadCreate):
    lead = store.create_lead(body)
    return {"ok": True, "data": lead}


@router.post("/leads/{lead_id}/convert")
def convert_lead(lead_id: str, body: LeadConvert, user: User = Depends(require_user)):
    try:
        deal = store.convert_lead(user, lead_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": deal}


@router.get("/contacts")
def contacts(q: str | None = None, ctype: str | None = None, user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_crm_contacts(q, ctype)}


@router.post("/contacts")
def create_contact(body: CrmContactCreate, user: User = Depends(require_user)):
    contact = store.create_crm_contact(body)
    return {"ok": True, "data": contact}


@router.get("/activities")
def activities(deal_id: str | None = None, lead_id: str | None = None, user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_crm_activities(deal_id, lead_id)}


@router.post("/activities")
def create_activity(body: CrmActivityCreate, user: User = Depends(require_user)):
    act = store.create_crm_activity(user, body)
    return {"ok": True, "data": act}


@router.post("/activities/{activity_id}/toggle")
def toggle_activity(activity_id: str, body: CrmActivityToggle, user: User = Depends(require_user)):
    try:
        act = store.toggle_crm_activity(activity_id, body.completed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": act}


@router.get("/invoices")
def invoices(deal_id: str | None = None, user: User = Depends(require_user)):
    return {"ok": True, "data": store.list_crm_invoices(deal_id)}


@router.post("/invoices")
def create_invoice(body: CrmInvoiceCreate, user: User = Depends(require_user)):
    inv = store.create_crm_invoice(body)
    return {"ok": True, "data": inv}


@router.post("/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: str, user: User = Depends(require_user)):
    try:
        inv = store.pay_crm_invoice(invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": inv}


@router.get("/analytics")
def analytics(user: User = Depends(require_user)):
    return {"ok": True, "data": store.crm_analytics(user)}
