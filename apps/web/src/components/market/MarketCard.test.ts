import { createElement, type ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { displayPriceTiyn, formatTiyn, type MarketCardItem } from "@/lib/market";
import { MarketCard } from "./MarketCard";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => createElement("a", { href }, children),
}));

function card(over: Partial<MarketCardItem> = {}): MarketCardItem {
  return {
    id: "mcat-6",
    name: "Арматура А500С Ø12",
    brand: "",
    category: "Металлопрокат",
    unit: "м",
    price_tiyn: 100_000,
    vat_included: false,
    vat_rate: 0,
    vat_label: "без НДС",
    stale: false,
    stale_label: "",
    availability: "в наличии",
    city: "Алматы",
    stock: "in_stock",
    lead_days: 0,
    supplier_id: "msup-4",
    supplier_name: "Поставщик 4",
    median_tiyn: null,
    median_label: "мало данных",
    rating: 4,
    deal_count: 2,
    review_count: 2,
    is_new: true,
    label: "Новый",
    badge: "",
    reliable: false,
    ...over,
  };
}

afterEach(() => {
  cleanup();
});

describe("MarketCard", () => {
  it("shows the large comparable price, the VAT mark, availability, and the request button", () => {
    const onAdd = vi.fn();
    render(createElement(MarketCard, { locale: "ru", item: card(), inBasket: false, onAdd }));
    const shown = formatTiyn(displayPriceTiyn(100_000, false, 0));
    expect(screen.getByRole("article").textContent).toContain(shown);
    expect(screen.getByText("без НДС")).toBeTruthy();
    expect(screen.getByText("в наличии")).toBeTruthy();
    expect(screen.getByText("мало данных")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "В заявку" }));
    expect(onAdd).toHaveBeenCalledOnce();
  });

  it("keeps an included-VAT price and the availability in days", () => {
    render(
      createElement(MarketCard, {
        locale: "ru",
        item: card({ vat_included: true, vat_rate: 16, vat_label: "с НДС", availability: "3 дней", lead_days: 3 }),
        inBasket: false,
        onAdd: () => undefined,
      }),
    );
    expect(screen.getByRole("article").textContent).toContain(formatTiyn(100_000));
    expect(screen.getByText("с НДС")).toBeTruthy();
    expect(screen.getByText("3 дней")).toBeTruthy();
    expect(screen.getByRole("button", { name: "В заявку" })).toBeTruthy();
  });

  it("shows the city market price and whether the buyer overpays", () => {
    render(
      createElement(MarketCard, {
        locale: "ru",
        item: card({
          median_label: "медиана",
          median_tiyn: 320_000,
          market_label: "Рыночная цена в Алматы",
          overpay_pct: 12,
          overpay_label: "дороже рынка на 12%",
          city: "Алматы",
        }),
        inBasket: false,
        onAdd: () => undefined,
      }),
    );
    const text = screen.getByRole("article").textContent || "";
    expect(text).toContain("Рыночная цена в Алматы");
    expect(text).toContain(formatTiyn(320_000));
    expect(text).toContain("дороже рынка на 12%");
    expect(text).not.toContain("мало данных");
  });
});
