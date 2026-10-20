"use client";

import { useEffect, useState } from "react";
import { AuthImage } from "@/components/media/AuthImage";
import {
  addObjectExpense,
  deleteObjectExpense,
  fetchObjectBudget,
  saveObjectBudget,
} from "@/lib/api";
import { money } from "@/lib/format";
import { ErrorRetry, LoadingSkeleton, useAsync, useGuardedSubmit } from "@/lib/useAsync";
import { t } from "@/i18n/messages";
import { budgetCategoryLabel } from "@/lib/budgetView";
import type { BudgetCategory, Locale, ObjectBudgetView } from "@/lib/types";
import { BudgetArticles } from "./BudgetArticles";

const field = "w-full min-h-12 border border-ink/15 bg-white px-3 text-sm";
const primary =
  "inline-flex min-h-12 w-full items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";

const CATEGORIES: BudgetCategory[] = ["materials", "works", "equipment", "other"];

function fill(template: string, values: Record<string, string | number>) {
  return Object.entries(values).reduce((text, [key, value]) => text.split(`{${key}}`).join(String(value)), template);
}

function share(value: number) {
  return Math.round(value * 100);
}

function whole(value: string) {
  const text = value.trim().replace(/\s/g, "");
  if (!/^\d+$/.test(text)) return null;
  const amount = Number(text);
  return Number.isSafeInteger(amount) && amount > 0 ? amount : null;
}

function planAmount(value: string) {
  const text = value.trim().replace(/\s/g, "");
  if (!text) return null;
  if (!/^\d+$/.test(text)) return undefined;
  const amount = Number(text);
  return Number.isSafeInteger(amount) ? amount : undefined;
}

function signalText(signal: ObjectBudgetView["signal"], m: ReturnType<typeof t>) {
  if (signal === "red") return m.budgetSignalOver;
  if (signal === "yellow") return m.budgetSignalClose;
  return m.budgetSignalOk;
}

function signalClass(signal: ObjectBudgetView["signal"]) {
  if (signal === "red") return "border-clay bg-rose-50";
  if (signal === "yellow") return "border-amber-500 bg-amber-50";
  return "border-pine bg-emerald-50";
}

function ForecastLine({
  data,
  locale,
  m,
}: {
  data: ObjectBudgetView;
  locale: Locale;
  m: ReturnType<typeof t>;
}) {
  if (data.overrun_kind === "actual" && data.overrun_kzt > 0) {
    return (
      <p className="text-sm font-medium" title={m.budgetForecastActualTip} data-forecast="actual">
        {m.budgetOverrunNow}: {money(data.overrun_kzt, locale)}
      </p>
    );
  }
  if (data.forecast_reason === "above_bound" && data.forecast_raw_kzt != null && data.forecast_bound_kzt != null) {
    const note = fill(m.budgetForecastBound, {
      raw: money(data.forecast_raw_kzt, locale),
      bound: money(data.forecast_bound_kzt, locale),
    });
    return (
      <p className="text-sm" title={note} data-forecast="bound">
        {note}
      </p>
    );
  }
  if (data.overrun_kind !== "forecast" || data.forecast_kzt == null || data.overrun_kzt <= 0) return null;
  const formula = fill(m.budgetForecastFormula, {
    fact: money(data.fact_kzt, locale),
    days: data.elapsed_days ?? 0,
    span: data.span_days ?? 0,
    forecast: money(data.forecast_kzt, locale),
  });
  return (
    <p className="text-sm font-medium" data-forecast="ok">
      <span title={formula}>
        {m.budgetForecast}: {money(data.overrun_kzt, locale)}
      </span>
      <span className="mt-1 block text-xs font-normal text-ink/70" title={formula}>
        {formula}
      </span>
    </p>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <p className="flex items-baseline justify-between gap-3 text-sm">
      <span className="text-ink/60">{label}</span>
      <span className="font-medium">{value}</span>
    </p>
  );
}

export function ObjectBudgetCard({ locale, projectId }: { locale: Locale; projectId: string }) {
  const m = t(locale);
  const query = useAsync(() => fetchObjectBudget(projectId), [projectId]);
  const [total, setTotal] = useState("");
  const [cats, setCats] = useState<Record<BudgetCategory, string>>({
    materials: "",
    works: "",
    equipment: "",
    other: "",
  });
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState<BudgetCategory>("materials");
  const [note, setNote] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoKey, setPhotoKey] = useState(0);
  const [formError, setFormError] = useState("");
  const planForm = useGuardedSubmit(m.budgetSaved, m.hubSaveError, () => query.reload());
  const expenseForm = useGuardedSubmit(m.budgetSaved, m.hubSaveError, () => {
    setAmount("");
    setNote("");
    setPhoto(null);
    setPhotoKey((value) => value + 1);
    query.reload();
  });

  useEffect(() => {
    if (!query.data) return;
    setTotal(query.data.plan.set ? String(query.data.plan.total_kzt) : "");
    setCats({
      materials: query.data.plan.materials_kzt == null ? "" : String(query.data.plan.materials_kzt),
      works: query.data.plan.works_kzt == null ? "" : String(query.data.plan.works_kzt),
      equipment: query.data.plan.equipment_kzt == null ? "" : String(query.data.plan.equipment_kzt),
      other: query.data.plan.other_kzt == null ? "" : String(query.data.plan.other_kzt),
    });
  }, [query.data]);

  if (query.loading || !query.data) {
    if (query.status === "error") {
      return <ErrorRetry message={m.hubLoadError} retryLabel={m.hubRetry} onRetry={query.reload} />;
    }
    return <LoadingSkeleton label={m.hubLoading} />;
  }

  const data = query.data;
  const used = data.used_pct == null ? "—" : `${Math.round(data.used_pct)}%`;

  function savePlan() {
    const source = total.trim() || (data.plan.set ? String(data.plan.total_kzt) : "");
    const planned = planAmount(source);
    if (planned == null) {
      setFormError(m.budgetNeedAmount);
      return;
    }
    const body: {
      total_kzt: number;
      materials_kzt?: number | null;
      works_kzt?: number | null;
      equipment_kzt?: number | null;
      other_kzt?: number | null;
    } = { total_kzt: planned };
    let sum = 0;
    let any = false;
    for (const key of CATEGORIES) {
      const raw = cats[key];
      if (!raw.trim()) continue;
      const value = planAmount(raw);
      if (value == null) {
        setFormError(m.budgetNeedAmount);
        return;
      }
      body[`${key}_kzt`] = value;
      sum += value;
      any = true;
    }
    if (!any && data.plan.set) {
      body.materials_kzt = data.plan.materials_kzt;
      body.works_kzt = data.plan.works_kzt;
      body.equipment_kzt = data.plan.equipment_kzt;
      body.other_kzt = data.plan.other_kzt;
    }
    if (any && sum > planned) {
      setFormError(m.budgetCatsOver);
      return;
    }
    setFormError("");
    void planForm.submit(async (key) => {
      await saveObjectBudget(projectId, body, key);
    });
  }

  return (
    <div className="grid gap-3">
      <section className={`grid gap-2 rounded-2xl border-2 p-4 ${signalClass(data.signal)}`} data-budget-card>
        <h2 className="text-base font-medium">{m.budgetCardTitle}</h2>
        {data.plan.set ? (
          <>
            <Line label={m.budgetPlan} value={money(data.plan.total_kzt, locale)} />
            <Line label={m.budgetFact} value={money(data.fact_kzt, locale)} />
            <Line label={m.budgetRemain} value={money(data.remaining_kzt ?? 0, locale)} />
            {data.plan_vs_chosen && (data.plan_vs_chosen.plan_kzt > 0 || data.plan_vs_chosen.chosen_kzt > 0) ? (
              <div className="grid gap-1 border-t border-ink/10 pt-2" data-plan-savings>
                {data.plan_vs_chosen.lines.map((line) => (
                  <p key={line.line_id} className="text-sm">
                    <span className="block break-words font-medium">{line.title}</span>
                    <span>
                      {m.budgetPlan} {money(line.plan_kzt, locale)} − {m.budgetChosenPrice} {money(line.chosen_kzt, locale)}
                    </span>
                    <span className="block">
                      {m.savingsAmount}: {money(line.saved_kzt, locale)}
                    </span>
                  </p>
                ))}
                <p className="text-sm">
                  {m.budgetPlan} {money(data.plan_vs_chosen.plan_kzt, locale)} − {m.budgetChosenPrice}{" "}
                  {money(data.plan_vs_chosen.chosen_kzt, locale)}
                </p>
                <p className="text-sm font-medium" data-total-saved>
                  {m.budgetTotalSaved}: {money(data.plan_vs_chosen.total_saved_kzt, locale)}
                </p>
              </div>
            ) : null}
            <p className="text-sm font-medium">
              {m.budgetUsed} {used} · {signalText(data.signal, m)}
            </p>
            <ForecastLine data={data} locale={locale} m={m} />
            <BudgetArticles locale={locale} plan={data.plan} factBy={data.fact_by_category} />
          </>
        ) : (
          <p className="text-sm">{m.budgetUnset}</p>
        )}
        {data.savings.base_kzt > 0 || data.savings.savings_kzt > 0 ? (
          <p className="text-sm">
            {m.savingsObject}: {money(data.savings.savings_kzt, locale)} ({share(data.savings.savings_pct)}%)
            {data.savings.requests ? ` · ${fill(m.savingsRequests, { n: data.savings.requests })}` : ""}
          </p>
        ) : null}
        {data.company.base_kzt > 0 || data.company.savings_kzt > 0 ? (
          <p className="break-words text-sm">
            {m.savingsCompany}
            {data.company.name ? ` · ${data.company.name}` : ""}: {money(data.company.savings_kzt, locale)} (
            {share(data.company.savings_pct)}%)
          </p>
        ) : null}
      </section>

      {data.can_edit ? (
        <form
          className="grid gap-3"
          data-expense-form
          onSubmit={(event) => {
            event.preventDefault();
            const value = whole(amount);
            if (value == null) {
              setFormError(m.budgetNeedAmount);
              return;
            }
            setFormError("");
            void expenseForm.submit(async (key) => {
              await addObjectExpense(projectId, { amount_kzt: value, category, note, photo }, key);
            });
          }}
        >
          {!data.plan.set ? (
            <label className="grid gap-1 text-sm">
              {m.budgetPlanPh}
              <input value={total} onChange={(event) => setTotal(event.target.value)} inputMode="numeric" className={field} />
            </label>
          ) : null}
          {!data.plan.set ? (
            <button type="button" className={primary} disabled={planForm.submitting} onClick={savePlan}>
              {m.budgetSavePlan}
            </button>
          ) : null}
          <p className="text-sm font-medium">{m.budgetExpense}</p>
          <label className="grid gap-1 text-sm">
            {m.budgetAmountPh}
            <input
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              inputMode="numeric"
              className={field}
              aria-label={m.budgetAmountPh}
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            {CATEGORIES.map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={category === item}
                className={`min-h-12 rounded-full border px-3 text-sm ${category === item ? "border-pine bg-pine text-paper" : "border-ink/15 bg-white"}`}
                onClick={() => setCategory(item)}
              >
                {budgetCategoryLabel(item, m)}
              </button>
            ))}
          </div>
          <button className={`${primary} scroll-mb-32`} data-save-expense disabled={expenseForm.submitting}>
            {m.budgetSaveExpense}
          </button>
          {formError ? <p className="text-sm text-rose-700">{formError}</p> : null}
          <details className="rounded-2xl border border-ink/10 bg-white/70 px-4 py-1">
            <summary className="cursor-pointer py-3 text-sm">{m.procMore}</summary>
            <div className="grid gap-3 pb-4">
              <p className="text-sm font-medium">{m.budgetCats}</p>
              {data.plan.set ? (
                <label className="grid gap-1 text-sm">
                  {m.budgetPlanPh}
                  <input value={total} onChange={(event) => setTotal(event.target.value)} inputMode="numeric" className={field} />
                </label>
              ) : null}
              {CATEGORIES.map((item) => (
                <label key={item} className="grid gap-1 text-sm">
                  {budgetCategoryLabel(item, m)}
                  <input
                    value={cats[item]}
                    onChange={(event) => setCats((prev) => ({ ...prev, [item]: event.target.value }))}
                    inputMode="numeric"
                    className={field}
                  />
                </label>
              ))}
              <button type="button" className={primary} disabled={planForm.submitting} onClick={savePlan}>
                {m.budgetSavePlan}
              </button>
              <label className="grid gap-1 text-sm">
                {m.budgetNote}
                <input value={note} onChange={(event) => setNote(event.target.value)} className={field} />
              </label>
              <label className="grid gap-1 text-sm">
                {m.budgetPhoto}
                <input
                  key={photoKey}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="block w-full text-sm"
                  onChange={(event) => setPhoto(event.target.files?.[0] || null)}
                />
              </label>
              <p className="text-sm text-ink/60">
                {m.budgetProcurement}: {money(data.procurement_kzt, locale)} · {m.budgetManual}: {money(data.manual_kzt, locale)}
              </p>
              {CATEGORIES.map((item) => (
                <p key={item} className="text-sm text-ink/70">
                  {budgetCategoryLabel(item, m)}: {money(data.fact_by_category[item] || 0, locale)}
                </p>
              ))}
              {data.expenses.map((item) => (
                <article key={item.id} className="grid gap-1 text-sm">
                  <p>
                    {money(item.amount_kzt, locale)} · {budgetCategoryLabel(item.category, m)}
                    {item.note ? ` · ${item.note}` : ""}
                  </p>
                  {item.has_photo ? (
                    <AuthImage
                      src={`/v1/site/projects/${projectId}/expenses/${item.id}/photo`}
                      alt={m.budgetPhoto}
                      className="max-h-40 w-full rounded-xl object-cover"
                    />
                  ) : null}
                  <button
                    type="button"
                    className="w-fit underline"
                    onClick={() =>
                      void deleteObjectExpense(projectId, item.id)
                        .then(() => query.reload())
                        .catch(() => setFormError(m.hubSaveError))
                    }
                  >
                    {m.procRemove}
                  </button>
                </article>
              ))}
            </div>
          </details>
        </form>
      ) : null}
    </div>
  );
}
