/** Storefront helpers: money, the request basket, and the labels the cards show. */

export const BASKET_KEY = "anyq-market-basket";

export const CATEGORY_TITLES = ["Металлопрокат", "Сэндвич-панели", "Крепёж", "Утеплитель"] as const;

export type MarketCardItem = {
  id: string;
  name: string;
  brand: string;
  category: string;
  unit: string;
  price_tiyn: number;
  vat_included: boolean;
  vat_rate: number;
  vat_label: string;
  stale: boolean;
  stale_label: string;
  availability: string;
  city: string;
  stock: string;
  lead_days: number;
  supplier_id: string;
  supplier_name: string;
  median_tiyn: number | null;
  median_label: string;
  rating: number;
  deal_count: number;
  review_count: number;
  is_new: boolean;
  label: string;
  badge: string;
  reliable: boolean;
  hidden?: boolean;
  source?: string;
};

export type BasketLine = {
  catalogId: string;
  name: string;
  unit: string;
  qty: number;
  supplierId: string;
  category: string;
};

export type OfferLineView = {
  id: string;
  name: string;
  unit: string;
  qty: number;
  comparable_tiyn: number;
  vat_label: string;
  analog_label: string;
  stale_label: string;
  suspicious: boolean;
  manual_review: boolean;
  median_label: string;
  lead_days: number;
};

export type OfferView = {
  id: string;
  supplier_name: string;
  status: string;
  comparable_tiyn: number;
  suspicious: boolean;
  manual_review: boolean;
  stale_label: string;
  analog_label: string;
  vat_label: string;
  esf_label: string;
  best: boolean;
  rating: number;
  deal_count: number;
  label: string;
  badge: string;
  lines: OfferLineView[];
};

export type RequestLineView = {
  id: string;
  catalog_id: string | null;
  name: string;
  unit: string;
  qty: number;
  category: string;
};

export type RequestView = {
  id: string;
  title: string;
  status: string;
  lines: RequestLineView[];
  suppliers: string[];
  offers: OfferView[];
};

export type StorefrontReview = {
  id: string;
  quality: number;
  delivery: number;
  price: number;
  communication: number;
  comment: string;
  supplier_reply: string;
};

export type Storefront = {
  id: string;
  name: string;
  city: string;
  vat_label: string;
  esf_label: string;
  categories: string[];
  delivery: boolean;
  delivery_cities: string[];
  min_order_tiyn: number;
  verification_label: string;
  rating: number;
  deal_count: number;
  review_count: number;
  label: string;
  badge: string;
  items: MarketCardItem[];
  total: number;
  reviews: StorefrontReview[];
};

export type OwnRating = {
  rating: number;
  deal_count: number;
  label: string;
  badge: string;
  tips: string[];
  name: string;
  is_new: boolean;
};

export type AssignedRequest = {
  id: string;
  title: string;
  status: string;
  created_at: string;
};

export function displayPriceTiyn(priceTiyn: number, vatIncluded: boolean, vatRate: number): number {
  if (vatIncluded) return priceTiyn;
  const rate = vatRate > 0 ? vatRate : 16;
  return Math.round((priceTiyn * (100 + rate)) / 100);
}

export function formatTiyn(tiyn: number): string {
  const value = tiyn / 100;
  const text = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
  return `${text} ₸`;
}

export function medianText(label: string, medianTiyn: number | null): string {
  if (label === "медиана" && medianTiyn != null) return `медиана ${formatTiyn(medianTiyn)}`;
  return label || "мало данных";
}

export function upsertBasket(lines: BasketLine[], next: BasketLine): BasketLine[] {
  if (lines.some((line) => line.catalogId === next.catalogId)) return lines;
  return [...lines, { ...next, qty: next.qty > 0 ? next.qty : 1 }];
}

export function removeBasket(lines: BasketLine[], catalogId: string): BasketLine[] {
  return lines.filter((line) => line.catalogId !== catalogId);
}

export function supplierIds(lines: BasketLine[]): string[] {
  return [...new Set(lines.map((line) => line.supplierId).filter(Boolean))];
}

export function readBasket(): BasketLine[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(BASKET_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as BasketLine[];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((line) => line && typeof line.catalogId === "string" && typeof line.name === "string");
  } catch {
    return [];
  }
}

export function writeBasket(lines: BasketLine[]) {
  window.localStorage.setItem(BASKET_KEY, JSON.stringify(lines));
}

export function lineFromCard(item: MarketCardItem): BasketLine {
  return {
    catalogId: item.id,
    name: item.name,
    unit: item.unit,
    qty: 1,
    supplierId: item.supplier_id,
    category: item.category,
  };
}
