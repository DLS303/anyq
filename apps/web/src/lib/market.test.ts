import { describe, expect, it } from "vitest";
import {
  displayPriceTiyn,
  formatTiyn,
  medianText,
  removeBasket,
  supplierIds,
  upsertBasket,
  type BasketLine,
} from "./market";

const line = (catalogId: string, supplierId: string): BasketLine => ({
  catalogId,
  name: catalogId,
  unit: "м",
  qty: 1,
  supplierId,
  category: "Металлопрокат",
});

describe("market money and basket", () => {
  it("grosses a price without VAT up to a comparable figure", () => {
    expect(displayPriceTiyn(100_000, false, 0)).toBe(116_000);
    expect(displayPriceTiyn(100_000, true, 16)).toBe(100_000);
  });

  it("formats tiyn as tenge", () => {
    expect(formatTiyn(450_000)).toMatch(/4[\s\u00a0\u202f]500 ₸/);
  });

  it("prints a median only when the card has one", () => {
    expect(medianText("медиана", 320_000)).toContain("медиана");
    expect(medianText("мало данных", null)).toBe("мало данных");
  });

  it("keeps one line per card and the distinct suppliers", () => {
    const once = upsertBasket([], line("a", "msup-1"));
    const twice = upsertBasket(once, line("a", "msup-1"));
    const both = upsertBasket(twice, line("b", "msup-2"));
    expect(twice).toHaveLength(1);
    expect(supplierIds(both)).toEqual(["msup-1", "msup-2"]);
    expect(removeBasket(both, "a").map((row) => row.catalogId)).toEqual(["b"]);
  });
});
