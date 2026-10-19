import { describe, expect, it } from "vitest";
import { budgetArticles } from "./budgetView";
import type { ObjectBudgetView } from "./types";

const plan: ObjectBudgetView["plan"] = {
  set: true,
  total_kzt: 2_000_000,
  materials_kzt: 1_200_000,
  works_kzt: 800_000,
  equipment_kzt: null,
  other_kzt: 0,
};

describe("budgetArticles", () => {
  it("keeps plan, fact and deviation for each fictional category", () => {
    const rows = budgetArticles(plan, {
      materials: 1_500_000,
      works: 200_000,
      equipment: 40_000,
    });
    const byName = Object.fromEntries(rows.map((row) => [row.category, row]));
    expect(byName.materials).toMatchObject({ plan: 1_200_000, fact: 1_500_000, deviation: 300_000 });
    expect(byName.works).toMatchObject({ plan: 800_000, fact: 200_000, deviation: -600_000 });
    expect(byName.equipment).toMatchObject({ plan: null, fact: 40_000, deviation: null });
    expect(byName.other).toMatchObject({ plan: 0, fact: 0, deviation: 0 });
  });
});
