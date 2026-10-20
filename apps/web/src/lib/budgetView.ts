import type { Msg } from "@/i18n/messages";
import type { BudgetCategory, ObjectBudgetView } from "@/lib/types";

export const BUDGET_CATEGORIES: BudgetCategory[] = ["materials", "works", "equipment", "other"];

export type BudgetArticle = {
  category: BudgetCategory;
  plan: number | null;
  fact: number;
  deviation: number | null;
};

export function budgetCategoryLabel(category: BudgetCategory, m: Msg) {
  if (category === "works") return m.budgetCatWorks;
  if (category === "equipment") return m.budgetCatEquipment;
  if (category === "other") return m.budgetCatOther;
  return m.budgetCatMaterials;
}

export function budgetArticles(
  plan: ObjectBudgetView["plan"],
  factBy: Partial<Record<BudgetCategory, number>>,
): BudgetArticle[] {
  return BUDGET_CATEGORIES.map((category) => {
    const planned = plan[`${category}_kzt`];
    const fact = factBy[category] ?? 0;
    return {
      category,
      plan: planned,
      fact,
      deviation: planned == null ? null : fact - planned,
    };
  });
}
