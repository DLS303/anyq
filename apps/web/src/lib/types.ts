export type Locale = "ru" | "kk";

export type Role =
  | "guest"
  | "buyer"
  | "owner"
  | "moderator"
  | "admin"
  | "specialist"
  | "contractor"
  | "supplier"
  | "supervisor"
  | "foreman"
  | "procurement"
  | "customer";

export type PlotStatus =
  | "draft"
  | "pending"
  | "needs_revision"
  | "published"
  | "rejected"
  | "reserved"
  | "sold"
  | "archived";

export type Purpose =
  | "izhs"
  | "lph"
  | "dacha"
  | "commercial"
  | "industrial"
  | "recreation"
  | "investment";

export type Utility = "connected" | "nearby" | "tu_received" | "absent";
export type Relief = "flat" | "slope" | "steep";

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  phone?: string;
  company?: string;
  company_bin?: string;
  city?: string;
  pilot?: string;
};

export type PlotDocs = {
  egrn: boolean;
  topo: boolean;
  apz: boolean;
  tu: boolean;
};

export type Plot = {
  id: string;
  slug: string;
  owner_id: string;
  cadastral_no: string;
  title_ru: string;
  title_kk: string;
  district: string;
  purpose: Purpose;
  area_sotka: number;
  price_kzt: number;
  divisible: boolean;
  land_category: string;
  status: PlotStatus;
  verified: boolean;
  trust_score: number;
  electricity: Utility;
  gas: Utility;
  water: Utility;
  sewage: Utility;
  access_road: Utility;
  relief: Relief;
  soil: string;
  encumbrances: string;
  registered_buildings: boolean;
  red_lines: boolean;
  power_protection_zone: boolean;
  gas_protection_zone: boolean;
  water_protection: boolean;
  docs: PlotDocs;
  moderation_note: string;
  description_ru: string;
  description_kk: string;
  polygon: [number, number][];
  photos: string[];
};

export type DevCalc = {
  utils_kzt: number;
  fence_kzt: number;
  foundation_kzt: number;
  total_kzt: number;
  disclaimer: string;
};

export type Inquiry = {
  id: string;
  plot_id: string;
  plot_title: string;
  buyer_id: string | null;
  name: string;
  phone: string;
  message: string;
  status: string;
  created_at: string;
};

export type ModuleInfo = {
  id: string;
  title: string;
  phase: number;
  status: "live" | "stub";
  notes: string;
};

export type SpecCategory = "survey" | "legal" | "architecture" | "smr" | "supervision" | "equipment";

export type Specialist = {
  id: string;
  slug: string;
  user_id: string;
  category: SpecCategory;
  company_ru: string;
  company_kk: string;
  bin: string;
  iin: string;
  license_no: string;
  license_cat: "I" | "II" | "III";
  license_verified: boolean;
  city: string;
  bio_ru: string;
  bio_kk: string;
  prices: { title_ru: string; title_kk: string; unit: string; price_kzt: number }[];
  portfolio: { title_ru: string; plot_id: string | null; photo: string }[];
  cover: string;
  rating: number;
  reviews_count: number;
};

export type ServiceOrder = {
  id: string;
  specialist_id: string;
  client_id: string;
  plot_id: string | null;
  message: string;
  status: string;
  quote_kzt: number | null;
  quote_term?: string;
  quote_comment?: string;
  deal_id: string | null;
  thread_id: string | null;
  created_at: string;
};

export type Review = {
  id: string;
  order_id: string;
  specialist_id: string;
  client_id: string;
  stars: number;
  text: string;
  created_at: string;
};

export type Funnel = "land_sale" | "design" | "construction" | "materials" | "legal";

export type LeadStatus = "new" | "contacted" | "qualified" | "converted" | "junk";

export type Lead = {
  id: string;
  title: string;
  name: string;
  phone: string;
  email: string;
  source: string;
  status: LeadStatus;
  funnel_target: Funnel;
  budget_kzt: number;
  plot_id: string | null;
  notes: string;
  responsible_id: string | null;
  responsible_name: string;
  deal_id: string | null;
  created_at: string;
};

export type ContactType = "client" | "contractor" | "landowner" | "supplier" | "investor";

export type CrmContact = {
  id: string;
  name: string;
  company_name: string;
  bin_iin: string;
  phone: string;
  email: string;
  city: string;
  contact_type: ContactType;
  trust_score: number;
  notes: string;
  total_deals_count: number;
  total_turnover_kzt: number;
  created_at: string;
};

export type ActivityType = "call" | "meeting" | "site_visit" | "task" | "invoice" | "note";

export type CrmActivity = {
  id: string;
  deal_id: string | null;
  lead_id: string | null;
  activity_type: ActivityType;
  title: string;
  description: string;
  due_date: string;
  completed: boolean;
  completed_at: string;
  author_id: string;
  author_name: string;
  created_at: string;
};

export type InvoiceStatus = "draft" | "sent" | "paid" | "overdue" | "cancelled";

export type CrmInvoice = {
  id: string;
  deal_id: string;
  number: string;
  title: string;
  amount_kzt: number;
  status: InvoiceStatus;
  payer_name: string;
  payer_iin_bin: string;
  escrow_enabled?: boolean;
  marked_manually?: boolean;
  can_mark_paid?: boolean;
  due_date: string;
  paid_at: string;
  created_at: string;
};

export type Deal = {
  id: string;
  funnel: Funnel;
  stage: string;
  title: string;
  client_id: string | null;
  client_name?: string;
  client_phone?: string;
  owner_id: string | null;
  specialist_id: string | null;
  specialist_name?: string;
  supplier_id?: string | null;
  plot_id: string | null;
  plot_title?: string;
  order_id: string | null;
  project_id?: string | null;
  inquiry_id?: string | null;
  responsible_id?: string | null;
  responsible_name?: string;
  amount_kzt: number;
  probability_pct?: number;
  source?: string;
  expected_close_date?: string;
  created_at: string;
  updated_at?: string;
};

export type CrmAnalytics = {
  total_deals: number;
  open_pipeline_kzt: number;
  won_deals_count: number;
  won_deals_kzt: number;
  total_leads: number;
  active_leads_count: number;
  lead_to_deal_pct: number | null;
  pending_activities_count: number;
  total_contacts: number;
  funnel_counts: Record<string, number>;
  stage_counts: Record<string, number>;
};

export type ChatThread = {
  id: string;
  user_a: string;
  user_b: string;
  plot_id: string | null;
  order_id: string | null;
  title: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  thread_id: string;
  author_id: string;
  text: string;
  created_at: string;
};

export type MaterialCat = "inert" | "concrete" | "brick" | "metal" | "lumber" | "roofing" | "mix";

export type Material = {
  id: string;
  slug: string;
  supplier_id: string;
  category: MaterialCat;
  title_ru: string;
  title_kk: string;
  unit: string;
  price_kzt: number;
  min_qty: number;
  stock: number;
  city: string;
  photo: string;
  description_ru: string;
  description_kk: string;
  published: boolean;
  certified_rk?: boolean;
};

export type MaterialOrder = {
  id: string;
  material_id: string;
  material_title: string;
  supplier_id: string;
  client_id: string;
  qty: number;
  unit: string;
  amount_kzt: number;
  plot_id: string | null;
  address: string;
  phone: string;
  status: string;
  created_at: string;
};

export type EstimateInput = {
  region: "almaty" | "astana" | "shymkent" | "west" | "north" | "other";
  house_type: "gasblock" | "brick" | "monolith" | "frame" | "sip";
  finish_level: "shell" | "prefinish" | "turnkey";
  area_m2: number;
  floors: number;
  seismic: boolean;
  basement: boolean;
  relief: "flat" | "slope" | "steep";
  utilities: {
    electricity: "connected" | "nearby" | "absent";
    water: "connected" | "nearby" | "absent";
    sewage: "connected" | "nearby" | "absent";
    gas: "connected" | "nearby" | "absent";
    road: "connected" | "nearby" | "absent";
  };
  contingency_pct: number;
  overhead_pct: number;
  profit_pct: number;
  include_vat: boolean;
};

export type EstimateLine = {
  code: string;
  section: string;
  title: string;
  unit: string;
  qty: number;
  unit_price_kzt: number;
  total_kzt: number;
  basis: string;
  confidence: "high" | "medium" | "low";
};

export type EstimateResult = {
  input: EstimateInput;
  market: Record<string, string | number>;
  quantities: Record<string, number>;
  lines: EstimateLine[];
  summary: {
    direct_kzt: number;
    overhead_kzt: number;
    contingency_kzt: number;
    profit_kzt: number;
    vat_kzt: number;
    total_kzt: number;
    per_m2_kzt: number;
    low_kzt: number;
    high_kzt: number;
  };
  warnings: string[];
};

export const DISTRICTS = [
  "Медеуский район",
  "Бостандыкский район",
  "Наурызбайский район",
  "Алатауский район",
  "Талгарский район",
  "Илийский район",
  "Жетысуский район",
  "Алмалинский район",
  "Ауэзовский район",
  "Турксибский район",
];

export type TaskStatus = "not_started" | "in_progress" | "done" | "blocked";

export type ScheduleTask = {
  id: string;
  project_id: string;
  title: string;
  start: string;
  finish: string;
  pct: number;
  status: TaskStatus;
  depends?: string;
};

export type ProcAccess = {
  member: boolean;
  can_request: boolean;
  can_offer: boolean;
  can_decide: boolean;
  can_invoice: boolean;
};

export type ProcRequestRow = {
  id: string;
  project_id: string;
  number: number;
  title: string;
  status: "draft" | "collecting" | "decided";
  created_at: string;
  created_by: string;
  lines: number;
  offers: number;
  documents: number;
};

export type ProcPrevious = {
  id: string;
  number: number;
  title: string;
  lines: number;
};

export type ProcList = {
  requests: ProcRequestRow[];
  access: ProcAccess;
  vat_rate: number;
  previous_completed?: ProcPrevious | null;
};

export type ProcOfferCell = {
  id: string;
  line_id: string;
  supplier_name: string;
  price_kzt: number;
  vat_included: boolean | null;
  qty_available: number | null;
  source_doc_id: string | null;
  source_label: string;
  offer_date: string;
  confirmed: boolean;
  note: string;
  delivery_term: string;
  is_best: boolean;
  is_selected: boolean;
  short: boolean;
  price_tiyn?: number;
  suspicious?: boolean;
  suspicion_confirmed?: boolean;
  source_kind?: string;
};

export type ProcSheetLine = {
  id: string;
  pos_no: string;
  title: string;
  unit: string;
  qty: number;
  note: string;
  selected_offer_id: string | null;
  status: string;
  status_code: "no_price" | "one_offer" | "no_compare" | "compared";
  comparable: boolean;
  best_offer_id: string | null;
  short_qty: boolean;
  short_available: number | null;
  short_need: number | null;
  offers: ProcOfferCell[];
  cells: Record<string, ProcOfferCell | null>;
};

export type ProcDocumentRow = {
  id: string;
  supplier_name: string;
  doc_number: string;
  doc_date: string;
  amount_kzt: number | null;
  duplicate_of: string | null;
  duplicate_reason: string;
  is_actual: boolean;
};

export type BudgetCategory = "materials" | "works" | "equipment" | "other";

export type SavingsOffer = {
  offer_id: string;
  supplier: string;
  price_kzt: number;
  vat_included: boolean | null;
  source_doc_id: string | null;
  source_label: string;
};

export type SavingsLine = {
  line_id: string;
  pos_no: string;
  title: string;
  unit: string;
  qty: number;
  included: boolean;
  reason: string;
  not_cheapest: boolean;
  selected: SavingsOffer | null;
  second: SavingsOffer | null;
  saving_kzt: number;
  base_kzt: number;
};

export type Overprice = {
  offer_id: string;
  line_id: string;
  title: string;
  unit: string;
  supplier: string;
  per_unit: number;
  total: number;
  total_kzt: number;
  pct: number;
};

export type ProcSavings = {
  savings_kzt: number;
  base_kzt: number;
  savings_pct: number;
  lines: SavingsLine[];
  overprice: Overprice[];
  duplicates: { id: string; duplicate_of: string | null; supplier_name: string; doc_number: string }[];
  inactive: { id: string }[];
  last_offer_date: string;
};

export type SavingsTotal = {
  savings_kzt: number;
  base_kzt: number;
  savings_pct: number;
  requests: number;
};

export type ObjectExpenseRow = {
  id: string;
  amount_kzt: number;
  category: BudgetCategory;
  note: string;
  has_photo: boolean;
  created_at: string;
};

export type ObjectBudgetView = {
  plan: {
    set: boolean;
    total_kzt: number;
    materials_kzt: number | null;
    works_kzt: number | null;
    equipment_kzt: number | null;
    other_kzt: number | null;
  };
  fact_kzt: number;
  fact_by_category: Record<BudgetCategory, number>;
  procurement_kzt: number;
  manual_kzt: number;
  remaining_kzt: number | null;
  used_pct: number | null;
  signal: "green" | "yellow" | "red";
  elapsed_share: number | null;
  elapsed_days: number | null;
  span_days: number | null;
  schedule_start: string;
  schedule_finish: string;
  forecast_kzt: number | null;
  forecast_raw_kzt: number | null;
  forecast_bound_kzt: number | null;
  forecast_reason: "no_dates" | "early" | "actual" | "above_bound" | "ok";
  overrun_kzt: number;
  overrun_kind: "actual" | "forecast" | "none";
  plan_vs_chosen?: {
    lines: {
      line_id: string;
      title: string;
      unit: string;
      qty: number;
      plan_kzt: number;
      chosen_kzt: number;
      saved_kzt: number;
    }[];
    plan_kzt: number;
    chosen_kzt: number;
    total_saved_kzt: number;
  };
  savings: SavingsTotal;
  company: SavingsTotal & { name: string };
  expenses: ObjectExpenseRow[];
  can_edit: boolean;
};

export type ProcSheet = {
  request: {
    id: string;
    number: number;
    title: string;
    status: "draft" | "collecting" | "decided";
  };
  suppliers: { name: string; total_kzt: number; priced_lines: number; vat_mixed: boolean }[];
  lines: ProcSheetLine[];
  summary: { lines: number; closed: number; no_price: number };
  documents: ProcDocumentRow[];
  access: ProcAccess;
  vat_rate: number;
};

export type ProcImportRow = {
  row: number;
  pos_no?: string;
  title?: string;
  unit?: string;
  qty?: number | null;
  note?: string;
  supplier_name?: string;
  price_kzt?: number | null;
  errors: string[];
};

export type ProcImportResult = {
  preview: boolean;
  created: number;
  updated: number;
  skipped: number;
  warnings: { row: number; code: string }[];
  rows: ProcImportRow[];
  contact_ignored: boolean;
};

export type ProcDocResult = {
  document: ProcDocumentRow;
  duplicate: boolean;
  duplicate_of: string | null;
  duplicate_reason: string;
  new_version_of_supplier: boolean;
};

export type ProcPickItem = {
  id?: string;
  title: string;
  unit: string;
  qty?: number;
  source: "recent" | "catalog";
};

export type ProcPicker = {
  recent: ProcPickItem[];
  catalog: ProcPickItem[];
};

export type ProcRepeatLine = {
  id: string;
  pos_no: string;
  title: string;
  unit: string;
  qty: number;
  note: string;
  selected_offer_id: string | null;
};
