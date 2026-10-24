"use client";

import { t } from "@/i18n/messages";
import { budgetArticles, budgetCategoryLabel } from "@/lib/budgetView";
import { money } from "@/lib/format";
import type { BudgetCategory, Locale, ObjectBudgetView } from "@/lib/types";

function signed(value: number, locale: Locale) {
  if (value > 0) return `+${money(value, locale)}`;
  return money(value, locale);
}

export function BudgetArticles({
  locale,
  plan,
  factBy,
}: {
  locale: Locale;
  plan: ObjectBudgetView["plan"];
  factBy: Partial<Record<BudgetCategory, number>>;
}) {
  const m = t(locale);
  const rows = budgetArticles(plan, factBy);
  return (
    <details className="rounded-xl bg-white/70 px-3" data-budget-articles>
      <summary className="min-h-12 cursor-pointer py-3 text-sm font-medium">{m.budgetArticles}</summary>
      <div className="grid gap-3 pb-3">
        {rows.map((row) => (
          <div key={row.category} className="grid gap-1 border-t border-ink/10 pt-3 text-sm" data-article={row.category}>
            <p className="font-medium">{budgetCategoryLabel(row.category, m)}</p>
            <p className="flex justify-between gap-3">
              <span className="text-ink/60">{m.budgetPlan}</span>
              <span>{row.plan == null ? "—" : money(row.plan, locale)}</span>
            </p>
            <p className="flex justify-between gap-3">
              <span className="text-ink/60">{m.budgetFact}</span>
              <span>{money(row.fact, locale)}</span>
            </p>
            <p className="flex justify-between gap-3" data-deviation={row.deviation ?? ""}>
              <span className="text-ink/60">{m.budgetDeviation}</span>
              <span className={row.deviation != null && row.deviation > 0 ? "font-medium text-rose-700" : "font-medium"}>
                {row.deviation == null ? "—" : signed(row.deviation, locale)}
              </span>
            </p>
          </div>
        ))}
      </div>
    </details>
  );
}
