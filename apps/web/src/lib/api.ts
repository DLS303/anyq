import { saveBlobDownload } from "./native";
import { preparePhoto, preparePhotos } from "./photos";
import type {
  ChatMessage,
  ChatThread,
  CrmActivity,
  CrmAnalytics,
  CrmContact,
  CrmInvoice,
  Deal,
  DevCalc,
  EstimateInput,
  EstimateResult,
  Inquiry,
  Lead,
  ModuleInfo,
  Plot,
  Material,
  MaterialOrder,
  ProcDocResult,
  ProcDocumentRow,
  ProcImportResult,
  ProcList,
  ProcOfferCell,
  ProcPicker,
  ProcRepeatLine,
  ProcSheet,
  Review,
  ServiceOrder,
  Specialist,
  User,
} from "./types";

export function getApiBase(): string {
  if (typeof window !== "undefined") return "";
  return process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8010";
}

export const API = getApiBase();

export const API_TIMEOUT_MS = 15_000;
export const API_GET_RETRIES = 2;
const RETRY_BASE_MS = 300;
const RETRY_STATUS = new Set([408, 429, 500, 502, 503, 504]);

type Envelope<T> = { ok: boolean; data: T; total?: number; detail?: string; [key: string]: unknown };

type RequestExtra = {
  email?: string;
  timeoutMs?: number;
  auth?: boolean;
};

export type RequestInitExtra = RequestInit & RequestExtra;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

function detailOf(json: unknown, fallback: string) {
  if (json && typeof json === "object" && "detail" in json) {
    const d = (json as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length && d[0] && typeof d[0] === "object" && "msg" in d[0]) {
      return String((d[0] as { msg: unknown }).msg);
    }
  }
  return fallback;
}

function applyAuth(headers: Headers) {
  if (typeof window === "undefined") return;
  const token = localStorage.getItem("superapp_token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
}

function isCredentialPost(path: string) {
  const bare = path.split("?")[0];
  return bare === "/v1/auth/login" || bare === "/v1/auth/register";
}

function sessionExpired(path: string, res: Response, headers: Headers) {
  if (res.status !== 401 || typeof window === "undefined") return;
  if (isCredentialPost(path) || !headers.has("Authorization")) return;
  localStorage.removeItem("superapp_user");
  localStorage.removeItem("superapp_token");
  const locale = window.location.pathname.startsWith("/kk") ? "kk" : "ru";
  if (!window.location.pathname.startsWith(`/${locale}/login`)) {
    window.location.replace(`/${locale}/login`);
  }
}

function anySignal(signals: AbortSignal[]) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.any === "function") {
    return AbortSignal.any(signals);
  }
  const controller = new AbortController();
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort();
      return controller.signal;
    }
    signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  return controller.signal;
}

function delay(ms: number, signal?: AbortSignal | null) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(finish, ms);
    function finish() {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }
    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function fetchOnce(path: string, init: RequestInitExtra | undefined, timeoutMs: number) {
  const headers = new Headers(init?.headers);
  const body = init?.body;
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (init?.auth !== false && !isCredentialPost(path)) applyAuth(headers);
  const caller = init?.signal ?? undefined;
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), timeoutMs);
  const signal = caller ? anySignal([caller, timeout.signal]) : timeout.signal;
  try {
    const res = await fetch(`${getApiBase()}${path}`, {
      method: init?.method,
      headers,
      body,
      cache: "no-store",
      signal,
      credentials: init?.credentials,
    });
    sessionExpired(path, res, headers);
    return res;
  } catch (error) {
    if (caller?.aborted) throw new DOMException("Aborted", "AbortError");
    if (timeout.signal.aborted) throw new ApiError("timeout", 408);
    throw error instanceof Error ? error : new ApiError("network", 0);
  } finally {
    clearTimeout(timer);
  }
}

export async function apiFetch(path: string, init?: RequestInitExtra): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const retryable = method === "GET" || method === "HEAD";
  const attempts = retryable ? API_GET_RETRIES + 1 : 1;
  const timeoutMs = init?.timeoutMs ?? API_TIMEOUT_MS;
  const caller = init?.signal ?? undefined;
  let lastResponse: Response | null = null;
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (attempt > 0) await delay(RETRY_BASE_MS * 2 ** (attempt - 1), caller);
    if (caller?.aborted) throw new DOMException("Aborted", "AbortError");
    try {
      const response = await fetchOnce(path, init, timeoutMs);
      if (retryable && attempt < attempts - 1 && RETRY_STATUS.has(response.status)) {
        await response.body?.cancel().catch(() => undefined);
        lastResponse = response;
        continue;
      }
      return response;
    } catch (error) {
      if (caller?.aborted || isAbortError(error)) throw error;
      if (error instanceof ApiError && error.status === 408) throw error;
      lastError = error;
      if (!retryable || attempt === attempts - 1) throw error;
    }
  }

  if (lastResponse) return lastResponse;
  throw lastError instanceof Error ? lastError : new ApiError("network", 0);
}

async function readBody<T>(res: Response): Promise<T> {
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(res.statusText || "network", res.status || 0);
  }
}

async function request<T>(path: string, init?: RequestInitExtra): Promise<T> {
  const res = await apiFetch(path, init);
  const json = await readBody<Envelope<T>>(res);
  if (!res.ok) throw new ApiError(detailOf(json, res.statusText), res.status);
  return json.data;
}

async function requestEnvelope<T>(path: string, init?: RequestInitExtra) {
  const res = await apiFetch(path, init);
  const json = await readBody<Envelope<T>>(res);
  if (!res.ok) throw new ApiError(detailOf(json, res.statusText), res.status);
  return json;
}

export function fetchPlots(params: Record<string, string | undefined> = {}, signal?: AbortSignal) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) q.set(k, v);
  }
  const s = q.toString();
  return request<Plot[]>(`/v1/plots${s ? `?${s}` : ""}`, { signal });
}

export async function fetchPlot(id: string, email?: string, signal?: AbortSignal) {
  void email;
  const json = await requestEnvelope<Plot>(`/v1/plots/${id}`, { signal });
  return {
    plot: json.data,
    calc: json.calc as DevCalc | undefined,
    favorite: Boolean(json.favorite),
  };
}

export function fetchModules(signal?: AbortSignal) {
  return request<ModuleInfo[]>("/v1/modules", { signal });
}

export function fetchMyPlots(email: string, signal?: AbortSignal) {
  return request<Plot[]>("/v1/cabinet/plots", { email, signal });
}

export function createPlot(email: string, body: Record<string, unknown>) {
  return request<Plot>("/v1/cabinet/plots", {
    method: "POST",
    email,
    body: JSON.stringify(body),
  });
}

export function fetchQueue(email: string, signal?: AbortSignal) {
  return request<Plot[]>("/v1/moderation/queue", { email, signal });
}

export function moderatePlot(
  email: string,
  id: string,
  action: "approve" | "revision" | "reject",
  comment = "",
) {
  return request<Plot>(`/v1/moderation/${id}`, {
    method: "POST",
    email,
    body: JSON.stringify({ action, comment }),
  });
}

export function sendInquiry(
  plotId: string,
  body: { name: string; phone: string; message: string },
  email?: string,
) {
  return request<Inquiry>(`/v1/plots/${plotId}/inquiries`, {
    method: "POST",
    email,
    body: JSON.stringify(body),
  });
}

export function fetchInquiries(email: string, signal?: AbortSignal) {
  return request<Inquiry[]>("/v1/cabinet/inquiries", { email, signal });
}

export function fetchFavorites(email: string, signal?: AbortSignal) {
  return request<Plot[]>("/v1/cabinet/favorites", { email, signal });
}

export function toggleFavorite(email: string, plotId: string) {
  return request<{ favorite: boolean; plot_id: string }>(`/v1/cabinet/favorites/${plotId}`, {
    method: "POST",
    email,
  });
}

export function updatePlot(email: string, id: string, body: Record<string, unknown>) {
  return request<Plot>(`/v1/cabinet/plots/${id}`, {
    method: "PATCH",
    email,
    body: JSON.stringify(body),
  });
}

export function submitPlot(email: string, id: string) {
  return request<Plot>(`/v1/cabinet/plots/${id}/submit`, { method: "POST", email });
}

export function suggestPlots(q: string, signal?: AbortSignal) {
  return request<{ kind: string; value: string; slug: string }[]>(
    `/v1/plots/suggest?q=${encodeURIComponent(q)}`,
    { signal },
  );
}

export async function uploadPhoto(email: string, file: File, projectId?: string, signal?: AbortSignal) {
  void email;
  const prepared = await preparePhoto(file);
  const fd = new FormData();
  fd.append("file", prepared);
  if (projectId) fd.append("project_id", projectId);
  const res = await apiFetch("/v1/cabinet/photos", { method: "POST", body: fd, signal });
  const json = await readBody<Envelope<{ url: string }>>(res);
  if (!res.ok) throw new ApiError(detailOf(json, res.statusText), res.status);
  return json.data.url;
}

export function saveSearch(email: string, title: string, params: Record<string, string | undefined>) {
  return request("/v1/cabinet/searches", {
    method: "POST",
    email,
    body: JSON.stringify({ title, params }),
  });
}

export function fetchSavedSearches(email: string, signal?: AbortSignal) {
  return request<{ id: string; title: string; params: Record<string, string> }[]>("/v1/cabinet/searches", {
    email,
    signal,
  });
}

export function fetchSpecialists(params: Record<string, string | undefined> = {}, signal?: AbortSignal) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return request<Specialist[]>(`/v1/specialists${s ? `?${s}` : ""}`, { signal });
}

export async function fetchSpecialist(id: string, signal?: AbortSignal) {
  const json = await requestEnvelope<Specialist>(`/v1/specialists/${id}`, { signal });
  return { specialist: json.data, reviews: (json.reviews as Review[] | undefined) ?? [] };
}

export function createOrder(email: string, specialistId: string, body: { plot_id?: string; message: string }) {
  return request<ServiceOrder>(`/v1/specialists/${specialistId}/orders`, {
    method: "POST",
    email,
    body: JSON.stringify({ specialist_id: specialistId, ...body }),
  });
}

export function fetchOrders(email: string, signal?: AbortSignal) {
  return request<ServiceOrder[]>("/v1/orders", { email, signal });
}

export function setOrderStatus(
  email: string,
  id: string,
  body: { status: string; quote_kzt?: number; quote_term?: string; quote_comment?: string },
) {
  return request<ServiceOrder>(`/v1/orders/${id}/status`, {
    method: "POST",
    email,
    body: JSON.stringify(body),
  });
}

export type ActVat = {
  act_date: string;
  no_vat: boolean;
  vat_rate: number;
  vat_percent: number;
  basis: string;
  prior_signed_kzt: number;
};

export function fetchActVat(actDate: string, noVat: boolean, projectId?: string, signal?: AbortSignal) {
  const q = new URLSearchParams({ act_date: actDate, no_vat: noVat ? "true" : "false" });
  if (projectId) q.set("project_id", projectId);
  return request<ActVat>(`/v1/acts/vat?${q}`, { signal });
}

export function reviewOrder(email: string, id: string, stars: number, text: string) {
  return request<Review>(`/v1/orders/${id}/review`, {
    method: "POST",
    email,
    body: JSON.stringify({ stars, text }),
  });
}

export function fetchFunnels(signal?: AbortSignal) {
  return request<Record<string, string[]>>("/v1/crm/funnels", { signal });
}

export function fetchDeals(email: string, funnel?: string, signal?: AbortSignal) {
  const q = funnel ? `?funnel=${funnel}` : "";
  return request<Deal[]>(`/v1/crm/deals${q}`, { email, signal });
}

export function moveDeal(email: string, id: string, stage: string) {
  return request<Deal>(`/v1/crm/deals/${id}/move`, {
    method: "POST",
    email,
    body: JSON.stringify({ stage }),
  });
}

export async function fetchDealDetail(email: string, id: string, signal?: AbortSignal) {
  void email;
  const json = await requestEnvelope<Deal>(`/v1/crm/deals/${id}`, { signal });
  return {
    deal: json.data,
    activities: (json.activities as CrmActivity[] | undefined) ?? [],
    invoices: (json.invoices as CrmInvoice[] | undefined) ?? [],
  };
}

export function createDeal(
  email: string,
  body: {
    funnel: string;
    stage?: string;
    title: string;
    amount_kzt: number;
    client_name?: string;
    client_phone?: string;
    plot_id?: string;
    specialist_id?: string;
    notes?: string;
  },
) {
  return request<Deal>("/v1/crm/deals", { method: "POST", email, body: JSON.stringify(body) });
}

export function dealToProject(
  email: string,
  id: string,
  body: { address?: string; finish?: string; budget_kzt?: number | null } = {},
) {
  return request<Record<string, unknown>>(`/v1/crm/deals/${id}/to-project`, {
    method: "POST",
    email,
    body: JSON.stringify(body),
  });
}

export function fetchLeads(email: string, status?: string, signal?: AbortSignal) {
  const q = status ? `?status=${status}` : "";
  return request<Lead[]>(`/v1/crm/leads${q}`, { email, signal });
}

export function createLead(body: {
  title: string;
  name: string;
  phone: string;
  email?: string;
  source?: string;
  funnel_target?: string;
  budget_kzt?: number;
  plot_id?: string;
  notes?: string;
}) {
  return request<Lead>("/v1/crm/leads", { method: "POST", body: JSON.stringify(body) });
}

export function convertLead(
  email: string,
  leadId: string,
  body: { funnel: string; deal_title?: string; amount_kzt?: number },
) {
  return request<Deal>(`/v1/crm/leads/${leadId}/convert`, { method: "POST", email, body: JSON.stringify(body) });
}

export function fetchContacts(
  email: string,
  params: { q?: string; ctype?: string } = {},
  signal?: AbortSignal,
) {
  const p = new URLSearchParams();
  if (params.q) p.set("q", params.q);
  if (params.ctype) p.set("ctype", params.ctype);
  const qs = p.toString();
  return request<CrmContact[]>(`/v1/crm/contacts${qs ? `?${qs}` : ""}`, { email, signal });
}

export function createContact(
  email: string,
  body: {
    name: string;
    company_name?: string;
    bin_iin?: string;
    phone: string;
    email?: string;
    city?: string;
    contact_type?: string;
    notes?: string;
  },
) {
  return request<CrmContact>("/v1/crm/contacts", { method: "POST", email, body: JSON.stringify(body) });
}

export function fetchActivities(
  email: string,
  params: { deal_id?: string; lead_id?: string } = {},
  signal?: AbortSignal,
) {
  const p = new URLSearchParams();
  if (params.deal_id) p.set("deal_id", params.deal_id);
  if (params.lead_id) p.set("lead_id", params.lead_id);
  const qs = p.toString();
  return request<CrmActivity[]>(`/v1/crm/activities${qs ? `?${qs}` : ""}`, { email, signal });
}

export function createActivity(
  email: string,
  body: {
    deal_id?: string;
    lead_id?: string;
    activity_type: string;
    title: string;
    description?: string;
    due_date?: string;
  },
) {
  return request<CrmActivity>("/v1/crm/activities", { method: "POST", email, body: JSON.stringify(body) });
}

export function toggleActivity(email: string, id: string, completed: boolean) {
  return request<CrmActivity>(`/v1/crm/activities/${id}/toggle`, {
    method: "POST",
    email,
    body: JSON.stringify({ completed }),
  });
}

export function fetchInvoices(email: string, deal_id?: string, signal?: AbortSignal) {
  const q = deal_id ? `?deal_id=${deal_id}` : "";
  return request<CrmInvoice[]>(`/v1/crm/invoices${q}`, { email, signal });
}

export function createInvoice(
  email: string,
  body: {
    deal_id: string;
    title: string;
    amount_kzt: number;
    payer_name: string;
    payer_iin_bin?: string;
    due_date?: string;
  },
) {
  return request<CrmInvoice>("/v1/crm/invoices", { method: "POST", email, body: JSON.stringify(body) });
}

export function payInvoice(email: string, id: string) {
  return request<CrmInvoice>(`/v1/crm/invoices/${id}/pay`, { method: "POST", email });
}

export function fetchCrmAnalytics(email: string, signal?: AbortSignal) {
  return request<CrmAnalytics>("/v1/crm/analytics", { email, signal });
}

export function fetchThreads(email: string, signal?: AbortSignal) {
  return request<ChatThread[]>("/v1/chat/threads", { email, signal });
}

export type ChatPeer = { id: string; full_name: string; role: string };

export function fetchChatPeers(signal?: AbortSignal) {
  return request<ChatPeer[]>("/v1/chat/peers", { signal });
}

export function openChatThread(peerId: string, title: string) {
  return request<ChatThread>("/v1/chat/threads", {
    method: "POST",
    body: JSON.stringify({ peer_id: peerId, title }),
  });
}

export async function fetchMessages(email: string, tid: string, signal?: AbortSignal) {
  void email;
  const json = await requestEnvelope<ChatMessage[]>(`/v1/chat/threads/${tid}/messages`, { signal });
  return { messages: json.data, thread: json.thread as ChatThread | undefined };
}

export function fetchMe(signal?: AbortSignal) {
  return request<User>("/v1/auth/me", { signal });
}

export function loginRequest(email: string, password: string, consentOfferPd: boolean, consentAi = false) {
  return request<{ user: User; token: string }>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, consent_offer_pd: consentOfferPd, consent_ai: consentAi }),
  });
}

export function registerRequest(body: {
  email: string;
  password: string;
  full_name: string;
  phone: string;
  company: string;
  company_bin: string;
  city: string;
  role: "buyer" | "contractor" | "supplier" | "owner";
  pilot: string;
  sku_title: string;
  sku_category: string;
  sku_unit: string;
  sku_price: number;
  sku_stock: number;
  consent_offer_pd: boolean;
  consent_ai?: boolean;
}) {
  return request<{ user: User; token: string }>("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchMaterials(params: Record<string, string | undefined> = {}, signal?: AbortSignal) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return request<Material[]>(`/v1/materials${s ? `?${s}` : ""}`, { signal });
}

export function fetchMaterial(id: string, signal?: AbortSignal) {
  return request<Material>(`/v1/materials/${id}`, { signal });
}

export function createMaterial(email: string, body: Record<string, unknown>) {
  return request<Material>("/v1/materials", { method: "POST", email, body: JSON.stringify(body) });
}

export function fetchSupplierMaterials(email: string, signal?: AbortSignal) {
  return request<Material[]>("/v1/cabinet/materials", { email, signal });
}

export function orderMaterial(
  email: string,
  body: { material_id: string; qty: number; plot_id?: string; address?: string; phone?: string },
) {
  return request<MaterialOrder>("/v1/material-orders", {
    method: "POST",
    email,
    body: JSON.stringify(body),
  });
}

export function fetchMaterialOrders(email: string, signal?: AbortSignal) {
  return request<MaterialOrder[]>("/v1/material-orders", { email, signal });
}

export function setMaterialOrderStatus(email: string, id: string, status: string) {
  return request<MaterialOrder>(`/v1/material-orders/${id}/status?status=${status}`, {
    method: "POST",
    email,
  });
}

export function calculateEstimate(body: EstimateInput) {
  return request<EstimateResult>("/v1/estimates/calculate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchProjects(signal?: AbortSignal) {
  return request<Record<string, unknown>[]>("/v1/site/projects", { signal });
}

export function fetchSiteBundle(id: string, signal?: AbortSignal) {
  return request<Record<string, unknown>>(`/v1/site/projects/${id}/bundle`, { signal });
}

export function postSite(
  path: string,
  email: string,
  body: Record<string, unknown> = {},
  idempotencyKey?: string,
  signal?: AbortSignal,
) {
  const headers = new Headers();
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  return request(`/v1/site/${path}`, { method: "POST", email, body: JSON.stringify(body), headers, signal });
}

export function deleteSite(path: string, signal?: AbortSignal) {
  return request(`/v1/site/${path}`, { method: "DELETE", signal });
}

export async function uploadDailyPhotos(logId: string, files: File[], signal?: AbortSignal) {
  const prepared = await preparePhotos(files);
  const fd = new FormData();
  for (const file of prepared) fd.append("files", file);
  const res = await apiFetch(`/v1/site/daily/${logId}/photos`, { method: "POST", body: fd, signal });
  const json = await readBody<
    Envelope<{
      log: Record<string, unknown>;
      added: { has_people: boolean; has_plates: boolean; taken_at?: string | null }[];
    }>
  >(res);
  if (!res.ok) throw new ApiError(detailOf(json, res.statusText), res.status);
  return json.data;
}

export type ConsentRow = {
  id: string;
  type: string;
  text_version: string;
  text_sha256: string;
  granted_at: string;
  revoked_at?: string | null;
  action?: "grant" | "revoke" | string;
};

export type ConsentDocument = {
  key: string;
  version: string;
  sha256: string;
};

export function createSiteProject(body: {
  title: string;
  address: string;
  deadline?: string;
  budget_kzt?: number;
}) {
  return request<{ id: string }>("/v1/site/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function addProjectMember(
  projectId: string,
  body: { email: string; role: string },
  idempotencyKey?: string,
  signal?: AbortSignal,
) {
  const headers = new Headers();
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  return request(`/v1/site/projects/${projectId}/members`, {
    method: "POST",
    body: JSON.stringify(body),
    headers,
    signal,
  });
}

export function removeProjectMember(projectId: string, userId: string) {
  return request(`/v1/site/projects/${projectId}/members/${userId}`, { method: "DELETE" });
}

export async function uploadDailyVoice(logId: string, file: Blob, durationS: number, signal?: AbortSignal) {
  const type = file.type || "audio/webm";
  const ext = type.includes("mp4") || type.includes("m4a") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
  const fd = new FormData();
  fd.append("file", file, `note.${ext}`);
  fd.append("duration_s", String(durationS));
  const res = await apiFetch(`/v1/site/daily/${logId}/voice`, { method: "POST", body: fd, signal });
  const json = await readBody<Envelope<Record<string, unknown>>>(res);
  if (!res.ok) throw new ApiError(detailOf(json, res.statusText), res.status);
  return json.data;
}

export function fetchConsents(signal?: AbortSignal) {
  return request<ConsentRow[]>("/v1/auth/consents", { signal });
}

export function fetchConsentDocuments(signal?: AbortSignal) {
  return request<ConsentDocument[]>("/v1/auth/consents/documents", { signal });
}

export async function fetchAuthorizedBlob(path: string, signal?: AbortSignal) {
  const res = await apiFetch(path, { signal });
  if (!res.ok) throw new ApiError(res.statusText || "file", res.status);
  return res.blob();
}

export function grantAiConsent() {
  return request<ConsentRow>("/v1/auth/consents/ai", { method: "POST" });
}

export function grantCrossBorderConsent(provider: string, country: string) {
  return request<ConsentRow>("/v1/auth/consents/cross-border", {
    method: "POST",
    body: JSON.stringify({ provider, country }),
  });
}

export function fetchBootstrap(signal?: AbortSignal) {
  return request<{ needs_owner: boolean; demo_mode: boolean }>("/v1/auth/bootstrap", { auth: false, signal });
}

export function revokeConsent(id: string) {
  return request<ConsentRow>(`/v1/auth/consents/${id}/revoke`, { method: "POST" });
}

export function sendChat(email: string, tid: string, text: string) {
  return request<ChatMessage>(`/v1/chat/threads/${tid}/messages`, {
    method: "POST",
    email,
    body: JSON.stringify({ text }),
  });
}

function withKey(idempotencyKey?: string) {
  const headers = new Headers();
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  return headers;
}

export function fetchProcRequests(projectId: string) {
  return request<ProcList>(`/v1/procurement/projects/${projectId}/requests`);
}

export function createProcRequest(projectId: string, title: string, idempotencyKey?: string) {
  return request<{ id: string }>(`/v1/procurement/projects/${projectId}/requests`, {
    method: "POST",
    body: JSON.stringify({ title }),
    headers: withKey(idempotencyKey),
  });
}

export function fetchProcSheet(requestId: string) {
  return request<ProcSheet>(`/v1/procurement/requests/${requestId}/sheet`);
}

export function fetchProcPicker(projectId: string, q = "") {
  const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return request<ProcPicker>(`/v1/procurement/projects/${projectId}/picker${query}`);
}

export function quickProcRequest(
  projectId: string,
  body: { title: string; unit: string; qty: number },
  idempotencyKey?: string,
) {
  return request<{ request: { id: string }; line: { id: string } }>(`/v1/procurement/projects/${projectId}/quick`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: withKey(idempotencyKey),
  });
}

export function repeatProcRequest(requestId: string, idempotencyKey?: string) {
  return request<{ request: { id: string; title: string }; lines: ProcRepeatLine[] }>(
    `/v1/procurement/requests/${requestId}/repeat`,
    { method: "POST", headers: withKey(idempotencyKey) },
  );
}

export function patchProcLine(lineId: string, qty: number) {
  return request<{ id: string; qty: number }>(`/v1/procurement/lines/${lineId}`, {
    method: "PATCH",
    body: JSON.stringify({ qty }),
  });
}

export function importProcLines(requestId: string, file: File, preview: boolean, idempotencyKey?: string) {
  const body = new FormData();
  body.append("file", file);
  const query = preview ? "?preview=1" : "";
  return request<ProcImportResult>(`/v1/procurement/requests/${requestId}/import-lines${query}`, {
    method: "POST",
    body,
    headers: withKey(idempotencyKey),
  });
}

export function importProcOffers(requestId: string, file: File, supplierName: string, idempotencyKey?: string) {
  const body = new FormData();
  body.append("file", file);
  body.append("supplier_name", supplierName);
  return request<ProcImportResult>(`/v1/procurement/requests/${requestId}/import-offers`, {
    method: "POST",
    body,
    headers: withKey(idempotencyKey),
  });
}

export function createProcOffer(
  lineId: string,
  payload: {
    supplier_name: string;
    price_kzt: number;
    vat_included: boolean | null;
    delivery_term: string;
    note: string;
    confirmed: boolean;
  },
  idempotencyKey?: string,
) {
  return request<ProcOfferCell>(`/v1/procurement/lines/${lineId}/offers`, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: withKey(idempotencyKey),
  });
}

export function deleteProcOffer(offerId: string) {
  return request<{ id: string }>(`/v1/procurement/offers/${offerId}`, { method: "DELETE" });
}

export function selectProcOffer(lineId: string, offerId: string | null, idempotencyKey?: string) {
  return request(`/v1/procurement/lines/${lineId}/select`, {
    method: "POST",
    body: JSON.stringify({ offer_id: offerId }),
    headers: withKey(idempotencyKey),
  });
}

export function selectProcBest(requestId: string, idempotencyKey?: string) {
  return request<ProcSheet>(`/v1/procurement/requests/${requestId}/select-best`, {
    method: "POST",
    headers: withKey(idempotencyKey),
  });
}

export function uploadProcDocument(
  requestId: string,
  file: File,
  fields: { supplier_name: string; doc_number: string; doc_date: string; amount_kzt: string },
  idempotencyKey?: string,
) {
  const body = new FormData();
  body.append("file", file);
  body.append("supplier_name", fields.supplier_name);
  body.append("doc_number", fields.doc_number);
  body.append("doc_date", fields.doc_date);
  if (fields.amount_kzt.trim()) body.append("amount_kzt", fields.amount_kzt.trim());
  return request<ProcDocResult>(`/v1/procurement/requests/${requestId}/documents`, {
    method: "POST",
    body,
    headers: withKey(idempotencyKey),
  });
}

export function setProcDocumentActual(documentId: string, isActual: boolean) {
  return request<ProcDocumentRow>(`/v1/procurement/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_actual: isActual }),
  });
}

async function authedBlob(path: string) {
  const headers = new Headers();
  applyAuth(headers);
  const res = await fetch(`${getApiBase()}${path}`, { headers, cache: "no-store" });
  sessionExpired(path, res, headers);
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = detailOf(await res.json(), message);
    } catch {
      /* the body is not JSON when the file itself is returned */
    }
    throw new ApiError(message, res.status);
  }
  return res.blob();
}

export async function downloadProc(path: string, filename: string) {
  const blob = await authedBlob(path);
  if (await saveBlobDownload(filename, blob)) return;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function openProcFile(path: string) {
  const blob = await authedBlob(path);
  const filename = decodeURIComponent(path.split("/").pop() || "file");
  if (await saveBlobDownload(filename, blob)) return;
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
