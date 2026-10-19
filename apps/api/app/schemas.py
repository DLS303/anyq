from typing import Literal

from pydantic import BaseModel, Field

Role = Literal[
    "guest",
    "buyer",
    "owner",
    "moderator",
    "admin",
    "specialist",
    "contractor",
    "supplier",
    "supervisor",
]

PlotStatus = Literal[
    "draft",
    "pending",
    "needs_revision",
    "published",
    "rejected",
    "reserved",
    "sold",
    "archived",
]

Purpose = Literal[
    "izhs",
    "lph",
    "dacha",
    "commercial",
    "industrial",
    "recreation",
    "investment",
]

Utility = Literal["connected", "nearby", "tu_received", "absent"]
Relief = Literal["flat", "slope", "steep"]
InquiryStatus = Literal["new", "seen", "closed"]


class User(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    phone: str = ""
    company: str = ""
    company_bin: str = ""
    city: str = ""
    pilot: str = ""


class PlotDocs(BaseModel):
    egrn: bool = False
    topo: bool = False
    apz: bool = False
    tu: bool = False


class Plot(BaseModel):
    id: str
    slug: str
    owner_id: str
    cadastral_no: str
    title_ru: str
    title_kk: str
    district: str
    purpose: Purpose
    area_sotka: float
    price_kzt: int
    divisible: bool = False
    land_category: str = "земли населённых пунктов"
    status: PlotStatus
    verified: bool = False
    trust_score: int = Field(default=0, ge=0, le=100)
    electricity: Utility
    gas: Utility
    water: Utility
    sewage: Utility
    access_road: Utility
    relief: Relief = "flat"
    soil: str = ""
    encumbrances: str = ""
    registered_buildings: bool = False
    red_lines: bool = False
    power_protection_zone: bool = False
    gas_protection_zone: bool = False
    water_protection: bool = False
    docs: PlotDocs = Field(default_factory=PlotDocs)
    moderation_note: str = ""
    description_ru: str = ""
    description_kk: str = ""
    polygon: list[list[float]]
    photos: list[str] = []


class PlotCreate(BaseModel):
    cadastral_no: str
    title_ru: str
    title_kk: str = ""
    district: str
    purpose: Purpose = "izhs"
    area_sotka: float
    price_kzt: int
    divisible: bool = False
    land_category: str = "земли населённых пунктов"
    electricity: Utility = "absent"
    gas: Utility = "absent"
    water: Utility = "absent"
    sewage: Utility = "absent"
    access_road: Utility = "absent"
    relief: Relief = "flat"
    soil: str = ""
    encumbrances: str = ""
    registered_buildings: bool = False
    red_lines: bool = False
    power_protection_zone: bool = False
    gas_protection_zone: bool = False
    water_protection: bool = False
    docs: PlotDocs = Field(default_factory=PlotDocs)
    description_ru: str = ""
    description_kk: str = ""
    polygon: list[list[float]] | None = None
    photos: list[str] = []


class ModerateBody(BaseModel):
    action: Literal["approve", "revision", "reject"]
    comment: str = ""


class InquiryCreate(BaseModel):
    name: str
    phone: str
    message: str = ""


class Inquiry(BaseModel):
    id: str
    plot_id: str
    plot_title: str
    buyer_id: str | None = None
    name: str
    phone: str
    message: str = ""
    status: InquiryStatus = "new"
    created_at: str


class Favorite(BaseModel):
    user_id: str
    plot_id: str


class SavedSearch(BaseModel):
    id: str
    user_id: str
    title: str
    params: dict = {}
    created_at: str


class SavedSearchCreate(BaseModel):
    title: str = ""
    params: dict = {}


class ModuleInfo(BaseModel):
    id: str
    title: str
    phase: int
    status: Literal["live", "stub"]
    notes: str


SpecCategory = Literal["survey", "legal", "architecture", "smr", "supervision", "equipment"]
LicenseCat = Literal["I", "II", "III"]
OrderStatus = Literal["requested", "quoted", "accepted", "in_progress", "completed", "cancelled"]
Funnel = Literal["land_sale", "design", "construction", "materials", "legal"]


FUNNEL_STAGES: dict[str, list[str]] = {
    "land_sale": ["lead", "audit", "viewing", "negotiation", "deposit", "won", "lost"],
    "design": ["brief", "sketch", "working", "expertise", "handover", "lost"],
    "construction": ["request", "quote", "estimate", "contract", "works", "acceptance", "won", "lost"],
    "materials": ["quote_req", "invoice_sent", "paid_reserved", "delivery", "accepted", "lost"],
    "legal": ["consult", "docs_collection", "approval", "registered", "lost"],
}

ORDER_FLOW: list[str] = ["requested", "quoted", "accepted", "in_progress", "completed"]


class PriceItem(BaseModel):
    title_ru: str
    title_kk: str = ""
    unit: str = "услуга"
    price_kzt: int


class PortfolioItem(BaseModel):
    title_ru: str
    plot_id: str | None = None
    photo: str = ""


class Specialist(BaseModel):
    id: str
    slug: str
    user_id: str
    category: SpecCategory
    company_ru: str
    company_kk: str = ""
    bin: str = ""
    iin: str = ""
    license_no: str = ""
    license_cat: LicenseCat = "II"
    license_verified: bool = False
    city: str = "Алматы"
    bio_ru: str = ""
    bio_kk: str = ""
    prices: list[PriceItem] = []
    portfolio: list[PortfolioItem] = []
    cover: str = ""


class OrderCreate(BaseModel):
    specialist_id: str
    plot_id: str | None = None
    message: str = ""


class ServiceOrder(BaseModel):
    id: str
    specialist_id: str
    client_id: str
    plot_id: str | None = None
    message: str = ""
    status: OrderStatus = "requested"
    quote_kzt: int | None = None
    quote_term: str = ""
    quote_comment: str = ""
    deal_id: str | None = None
    thread_id: str | None = None
    created_at: str
    updated_at: str = ""


class ReviewCreate(BaseModel):
    stars: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)


class OrderStatusUpdate(BaseModel):
    status: str
    quote_kzt: int | None = None
    quote_term: str = Field(default="", max_length=120)
    quote_comment: str = Field(default="", max_length=2000)


class Review(BaseModel):
    id: str
    order_id: str
    specialist_id: str
    client_id: str
    stars: int
    text: str = ""
    created_at: str


LeadStatus = Literal["new", "contacted", "qualified", "converted", "junk"]


class Lead(BaseModel):
    id: str
    title: str
    name: str
    phone: str
    email: str = ""
    source: str = "Сайт"
    status: LeadStatus = "new"
    funnel_target: Funnel = "construction"
    budget_kzt: int = 0
    plot_id: str | None = None
    notes: str = ""
    responsible_id: str | None = None
    responsible_name: str = "Асет Сагинтаев"
    deal_id: str | None = None
    created_at: str


class LeadCreate(BaseModel):
    title: str
    name: str
    phone: str
    email: str = ""
    source: str = "Сайт"
    funnel_target: Funnel = "construction"
    budget_kzt: int = 0
    plot_id: str | None = None
    notes: str = ""


class LeadConvert(BaseModel):
    funnel: Funnel = "construction"
    deal_title: str = ""
    amount_kzt: int = 0


ContactType = Literal["client", "contractor", "landowner", "supplier", "investor"]


class CrmContact(BaseModel):
    id: str
    name: str
    company_name: str = ""
    bin_iin: str = ""
    phone: str
    email: str = ""
    city: str = "Алматы"
    contact_type: ContactType = "client"
    trust_score: int = 85
    notes: str = ""
    owner_id: str = ""
    total_deals_count: int = 0
    total_turnover_kzt: int = 0
    created_at: str


class CrmContactCreate(BaseModel):
    name: str
    company_name: str = ""
    bin_iin: str = ""
    phone: str
    email: str = ""
    city: str = "Алматы"
    contact_type: ContactType = "client"
    notes: str = ""


ActivityType = Literal["call", "meeting", "site_visit", "task", "invoice", "note"]


class CrmActivity(BaseModel):
    id: str
    deal_id: str | None = None
    lead_id: str | None = None
    activity_type: ActivityType = "note"
    title: str
    description: str = ""
    due_date: str = ""
    completed: bool = False
    completed_at: str = ""
    author_id: str = ""
    author_name: str = "Менеджер"
    created_at: str


class CrmActivityCreate(BaseModel):
    deal_id: str | None = None
    lead_id: str | None = None
    activity_type: ActivityType = "note"
    title: str
    description: str = ""
    due_date: str = ""


class CrmActivityToggle(BaseModel):
    completed: bool


InvoiceStatus = Literal["draft", "sent", "paid", "overdue", "cancelled"]


class CrmInvoice(BaseModel):
    id: str
    deal_id: str
    number: str
    title: str
    amount_kzt: int
    status: InvoiceStatus = "draft"
    payer_name: str
    payer_iin_bin: str = ""
    escrow_enabled: bool = False
    marked_manually: bool = False
    due_date: str = ""
    paid_at: str = ""
    created_at: str


class CrmInvoiceCreate(BaseModel):
    deal_id: str
    title: str
    amount_kzt: int
    payer_name: str
    payer_iin_bin: str = ""
    escrow_enabled: bool = False
    due_date: str = ""


class Deal(BaseModel):
    id: str
    funnel: Funnel
    stage: str
    title: str
    client_id: str | None = None
    client_name: str = ""
    client_phone: str = ""
    owner_id: str | None = None
    specialist_id: str | None = None
    specialist_name: str = ""
    supplier_id: str | None = None
    plot_id: str | None = None
    plot_title: str = ""
    order_id: str | None = None
    project_id: str | None = None
    inquiry_id: str | None = None
    responsible_id: str | None = None
    responsible_name: str = "Асет Сагинтаев"
    amount_kzt: int = 0
    probability_pct: int = 60
    source: str = "Сайт"
    expected_close_date: str = ""
    created_at: str
    updated_at: str = ""


class DealCreate(BaseModel):
    funnel: Funnel = "construction"
    stage: str = "lead"
    title: str
    amount_kzt: int = 0
    client_name: str = ""
    client_phone: str = ""
    plot_id: str | None = None
    specialist_id: str | None = None
    notes: str = ""


class DealMove(BaseModel):
    stage: str


class DealToProject(BaseModel):
    address: str = ""
    finish: str = ""
    budget_kzt: int | None = None


class ChatThread(BaseModel):
    id: str
    user_a: str
    user_b: str
    plot_id: str | None = None
    order_id: str | None = None
    title: str = ""
    updated_at: str


class ChatMessage(BaseModel):
    id: str
    thread_id: str
    author_id: str
    text: str
    created_at: str


class MessageCreate(BaseModel):
    text: str


class ThreadCreate(BaseModel):
    peer_id: str
    plot_id: str | None = None
    order_id: str | None = None
    title: str = ""


MaterialCat = Literal["inert", "concrete", "brick", "metal", "lumber", "roofing", "mix"]
MaterialOrderStatus = Literal["requested", "confirmed", "shipped", "delivered", "cancelled"]


class Material(BaseModel):
    id: str
    slug: str
    supplier_id: str
    category: MaterialCat
    title_ru: str
    title_kk: str = ""
    unit: str = "т"
    price_kzt: int
    min_qty: float = 1
    stock: float = 0
    city: str = "Алматы"
    photo: str = ""
    description_ru: str = ""
    description_kk: str = ""
    published: bool = True


class MaterialCreate(BaseModel):
    category: MaterialCat = "inert"
    title_ru: str
    title_kk: str = ""
    unit: str = "т"
    price_kzt: int
    min_qty: float = 1
    stock: float = 0
    city: str = "Алматы"
    photo: str = ""
    description_ru: str = ""
    description_kk: str = ""


class MaterialOrderCreate(BaseModel):
    material_id: str
    qty: float
    plot_id: str | None = None
    address: str = ""
    phone: str = ""


class MaterialOrder(BaseModel):
    id: str
    material_id: str
    material_title: str
    supplier_id: str
    client_id: str
    qty: float
    unit: str
    amount_kzt: int
    plot_id: str | None = None
    address: str = ""
    phone: str = ""
    status: MaterialOrderStatus = "requested"
    created_at: str


class RegisterBody(BaseModel):
    email: str
    password: str
    full_name: str
    phone: str = ""
    company: str = ""
    company_bin: str = ""
    city: str = "Алматы"
    role: Literal["buyer", "contractor", "supplier"]
    pilot: str = ""
    sku_title: str = ""
    sku_category: MaterialCat = "concrete"
    sku_unit: str = "т"
    sku_price: int = 0
    sku_stock: float = 0
    consent_offer_pd: bool = False
    consent_ai: bool = False


class LoginBody(BaseModel):
    email: str
    password: str
    consent_offer_pd: bool = False
    consent_ai: bool = False


class ConsentRecord(BaseModel):
    id: str
    user_id: str
    type: Literal["offer_pd", "cross_border", "ai"] = "offer_pd"
    text_version: str
    text_sha256: str
    granted_at: str
    action: Literal["grant", "revoke"] = "grant"
    revoked_at: str | None = None
    ip: str = ""
    user_agent: str = ""
    login: str = ""
    provider: str = ""
    country: str = ""
    privacy_version: str = ""
    privacy_sha256: str = ""


class CrossBorderConsentBody(BaseModel):
    provider: str = Field(min_length=1, max_length=120)
    country: str = Field(min_length=2, max_length=80)


class StoredUpload(BaseModel):
    id: str
    owner_id: str
    name: str
    content_type: str
    created_at: str
    project_id: str | None = None
    kind: Literal["upload", "original", "public", "voice"] = "upload"
    daily_log_id: str | None = None
