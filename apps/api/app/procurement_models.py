"""Procurement request, lines, supplier offers, and invoices."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


def kzt_to_tiyn(price: float) -> int:
    """Store money as integer tiyn. 1 tenge is 100 tiyn."""
    tiyn = int((Decimal(str(price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if tiyn <= 0:
        raise ValueError("Цена должна быть больше нуля")
    return tiyn


class ProcOffer(BaseModel):
    id: str
    line_id: str
    supplier_name: str
    price_kzt: float = Field(gt=0)
    price_tiyn: int = 0
    vat_included: bool | None = None
    qty_available: float | None = None
    source_doc_id: str | None = None
    source_label: str = ""
    source_kind: str = ""
    offer_date: str = ""
    confirmed: bool = False
    suspicious: bool = False
    suspicion_confirmed: bool = False
    note: str = ""
    delivery_term: str = ""

    @model_validator(mode="after")
    def normalize_tiyn(self):
        if self.price_tiyn > 0:
            self.price_kzt = self.price_tiyn / 100
        else:
            self.price_tiyn = kzt_to_tiyn(self.price_kzt)
            self.price_kzt = self.price_tiyn / 100
        return self


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
    company_id: str = ""
    supplier_id: str = ""
    number: str = ""
    deleted: bool = False
