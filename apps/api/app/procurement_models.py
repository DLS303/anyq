"""Procurement request, lines, supplier offers, and invoices."""

from typing import Literal

from pydantic import BaseModel, Field

RequestStatus = Literal["draft", "collecting", "decided"]


class ProcRequest(BaseModel):
    id: str
    project_id: str
    number: int = Field(ge=1)
    title: str
    status: RequestStatus = "draft"
    created_at: str
    created_by: str
    shared: bool = True
    repeated_from: str | None = None


class ProcLine(BaseModel):
    id: str
    request_id: str
    pos_no: str
    title: str
    unit: str
    qty: float = Field(gt=0)
    note: str = ""
    selected_offer_id: str | None = None
    reference_price_kzt: float | None = None
    reference_vat_included: bool | None = None
    reference_source: str = ""
    requires_approval: bool = False
    approval_id: str | None = None
    brand: str = ""


class ProcOffer(BaseModel):
    id: str
    line_id: str
    supplier_name: str
    price_kzt: float = Field(gt=0)
    vat_included: bool | None = None
    qty_available: float | None = None
    source_doc_id: str | None = None
    source_label: str = ""
    offer_date: str = ""
    confirmed: bool = False
    note: str = ""
    delivery_term: str = ""
    offered_brand: str = ""


class ProcDocument(BaseModel):
    id: str
    request_id: str
    supplier_name: str
    doc_number: str = ""
    doc_date: str = ""
    amount_kzt: float | None = None
    stored_name: str
    mime: str
    size: int = Field(ge=0)
    sha256: str
    uploaded_at: str
    uploaded_by: str
    duplicate_of: str | None = None
    duplicate_reason: str = ""
    is_actual: bool = True
