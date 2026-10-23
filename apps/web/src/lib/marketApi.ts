import { ApiError, apiFetch, type RequestInitExtra } from "./api";
import type {
  AssignedRequest,
  MarketCardItem,
  OwnRating,
  RequestView,
  Storefront,
} from "./market";

type Envelope<T> = { ok?: boolean; data: T; total?: number; detail?: unknown };

async function read<T>(path: string, init?: RequestInitExtra): Promise<Envelope<T>> {
  const res = await apiFetch(path, init);
  let json: Envelope<T>;
  try {
    json = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.statusText || "network", res.status || 0);
  }
  if (!res.ok) {
    const detail = json.detail;
    const message = typeof detail === "string" ? detail : res.statusText || "Ошибка";
    throw new ApiError(message, res.status);
  }
  return json;
}

function data<T>(path: string, init?: RequestInitExtra) {
  return read<T>(path, init).then((json) => json.data);
}

export function fetchHome(signal?: AbortSignal) {
  return data<{ categories: { id: string; title: string }[] }>("/v1/market/home", { signal });
}

export function fetchCities(signal?: AbortSignal) {
  return data<string[]>("/v1/market/cities", { signal });
}

export function fetchCatalog(
  params: { q?: string; category?: string; city?: string; priceMax?: number; limit?: number; offset?: number },
  signal?: AbortSignal,
) {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  if (params.category) query.set("category", params.category);
  if (params.city) query.set("city", params.city);
  if (params.priceMax) query.set("price_max", String(params.priceMax));
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return read<MarketCardItem[]>(`/v1/market/catalog?${query}`, { signal }).then((json) => ({
    items: json.data,
    total: typeof json.total === "number" ? json.total : json.data.length,
  }));
}

export function fetchSupplier(id: string, signal?: AbortSignal) {
  return data<Storefront>(`/v1/market/suppliers/${id}?limit=40`, { signal });
}

export function contactSupplier(id: string) {
  return data<RequestView>(`/v1/market/suppliers/${id}/contact`, { method: "POST" });
}

export function createRequest(body: {
  title: string;
  supplier_ids: string[];
  lines: { catalog_id: string; name: string; unit: string; qty: number; category: string }[];
}) {
  return data<RequestView>("/v1/market/requests", { method: "POST", body: JSON.stringify(body) });
}

export function fetchRequest(id: string, signal?: AbortSignal) {
  return data<RequestView>(`/v1/market/requests/${id}`, { signal });
}

export function repeatRequest(id: string) {
  return data<RequestView>(`/v1/market/requests/${id}/repeat`, { method: "POST" });
}

export function selectOffer(id: string) {
  return data<{ deal_id: string; offer_id: string; status: string }>(`/v1/market/offers/${id}/select`, {
    method: "POST",
  });
}

export function submitOffer(body: {
  request_id: string;
  source: string;
  lines: {
    request_line_id: string;
    catalog_id: string | null;
    name: string;
    unit: string;
    qty: number;
    price_tiyn: number;
    analog: boolean;
    source: string;
  }[];
}) {
  return data<{ id: string }>("/v1/market/offers", { method: "POST", body: JSON.stringify(body) });
}

export function fetchOwnItems(signal?: AbortSignal) {
  return data<MarketCardItem[]>("/v1/market/my/items", { signal });
}

export function saveOwnItem(body: Record<string, unknown>, id?: string) {
  const path = id ? `/v1/market/my/items/${id}` : "/v1/market/my/items";
  return data<MarketCardItem>(path, { method: id ? "PATCH" : "POST", body: JSON.stringify(body) });
}

export function hideOwnItem(id: string, hidden: boolean) {
  return data<{ id: string; hidden: boolean }>(`/v1/market/my/items/${id}/hide`, {
    method: "POST",
    body: JSON.stringify({ hidden }),
  });
}

export function importPrices(file: File) {
  const body = new FormData();
  body.append("file", file);
  return data<{ saved: number }>("/v1/market/my/import", { method: "POST", body });
}

export function fetchOwnRating(signal?: AbortSignal) {
  return data<OwnRating>("/v1/market/my/rating", { signal });
}

export function fetchAssigned(signal?: AbortSignal) {
  return data<AssignedRequest[]>("/v1/market/assigned", { signal });
}
