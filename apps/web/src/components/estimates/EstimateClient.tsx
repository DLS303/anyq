"use client";

import { Fragment, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Calculator, Download, FileSpreadsheet, RefreshCw, Briefcase, CheckCircle2 } from "lucide-react";
import { calculateEstimate, createDeal } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import type { EstimateInput, EstimateResult, Locale } from "@/lib/types";

const REGIONS = [
  ["almaty", "Алматы"],
  ["astana", "Астана"],
  ["shymkent", "Шымкент"],
  ["west", "Запад РК"],
  ["north", "Север/центр"],
  ["other", "Другой регион"],
] as const;

const HOUSE_TYPES = [
  ["gasblock", "Газоблок"],
  ["brick", "Кирпич"],
  ["monolith", "Монолит"],
  ["frame", "Каркас"],
  ["sip", "СИП"],
] as const;

const FINISH = [
  ["shell", "Черновой"],
  ["prefinish", "Предчистовой"],
  ["turnkey", "Чистовой"],
] as const;

const UTILITY = [
  ["connected", "Подключено"],
  ["nearby", "Рядом"],
  ["absent", "Нет"],
] as const;

const DEFAULT_INPUT: EstimateInput = {
  region: "almaty",
  house_type: "gasblock",
  finish_level: "prefinish",
  area_m2: 160,
  floors: 2,
  seismic: true,
  basement: false,
  relief: "flat",
  utilities: {
    electricity: "nearby",
    water: "nearby",
    sewage: "absent",
    gas: "nearby",
    road: "connected",
  },
  contingency_pct: 7,
  overhead_pct: 10,
  profit_pct: 8,
  include_vat: true,
};

export function EstimateClient({ locale, embedded = false }: { locale: Locale; embedded?: boolean }) {
  const router = useRouter();
  const { user } = useAuth();
  const [form, setForm] = useState<EstimateInput>(DEFAULT_INPUT);
  const [result, setResult] = useState<EstimateResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [dealCreated, setDealCreated] = useState("");
  const [error, setError] = useState("");

  async function createDealInCrm() {
    if (!result) return;
    try {
      if (!user) {
        window.dispatchEvent(
          new CustomEvent("anyq-toast", {
            detail: { message: "Сначала зарегистрируйте компанию для пилота Engicon" },
          }),
        );
        router.push(`/${locale}/login?mode=register`);
        return;
      }
      const title = `Строительство: ${form.area_m2} м² (${form.house_type})`;
      const d = await createDeal(user.email, {
        funnel: "construction",
        title,
        amount_kzt: result.summary.total_kzt,
        client_name: user.company || user.full_name,
        notes: `Смета BOQ: ${form.area_m2} м², ${form.floors} эт., отделка ${form.finish_level}, регион ${form.region}`,
      });
      setDealCreated(d.id);
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("anyq-toast", {
            detail: { message: `Сделка #${d.id} по смете успешно создана в воронке CRM!` },
          })
        );
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  const sections = useMemo(() => {
    const grouped = new Map<string, EstimateResult["lines"]>();
    for (const line of result?.lines || []) {
      grouped.set(line.section, [...(grouped.get(line.section) || []), line]);
    }
    return [...grouped.entries()];
  }, [result]);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      setResult(await calculateEstimate(form));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось посчитать смету");
    } finally {
      setBusy(false);
    }
  }

  function patch(next: Partial<EstimateInput>) {
    setForm((prev) => ({ ...prev, ...next }));
  }

  function patchUtility(key: keyof EstimateInput["utilities"], value: "connected" | "nearby" | "absent") {
    setForm((prev) => ({ ...prev, utilities: { ...prev.utilities, [key]: value } }));
  }

  function downloadCsv() {
    if (!result) return;
    const header = ["code", "section", "title", "unit", "qty", "unit_price_kzt", "total_kzt", "basis"];
    const rows = result.lines.map((x) =>
      [x.code, x.section, x.title, x.unit, x.qty, x.unit_price_kzt, x.total_kzt, x.basis]
        .map((v) => `"${String(v).replaceAll('"', '""')}"`)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `anyq-estimate-${form.region}-${form.area_m2}m2.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="grid gap-8">
      <section className="grid gap-6 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.16em] text-ink/45">BOQ · рынок РК · ИЖС</p>
          {embedded ? (
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Сметы</h2>
          ) : (
            <h1 className="mt-2 text-4xl font-medium tracking-tight">Автосмета для строителей</h1>
          )}
          <p className="mt-3 max-w-2xl text-[15px] leading-6 text-ink/60">
            Предварительный бюджет по дому, участку и наружным сетям: объемы, работы, материалы, накладные,
            прибыль, риск и НДС 16%.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Kpi label="Регион" value={REGIONS.find(([id]) => id === form.region)?.[1] || "РК"} />
          <Kpi label="Площадь" value={`${form.area_m2} м2`} />
          <Kpi label="Дата базы" value="09.2026" />
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <form
          className="glass-strong h-fit rounded-frost p-5"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <div className="mb-5 flex items-center gap-2">
            <Calculator className="h-5 w-5 text-pine" />
            <h2 className="text-lg font-medium">Параметры</h2>
          </div>

          <Field label="Регион">
            <select value={form.region} onChange={(e) => patch({ region: e.target.value as EstimateInput["region"] })} className="w-full border border-ink/15 px-3 py-2 text-sm">
              {REGIONS.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Конструктив">
            <select value={form.house_type} onChange={(e) => patch({ house_type: e.target.value as EstimateInput["house_type"] })} className="w-full border border-ink/15 px-3 py-2 text-sm">
              {HOUSE_TYPES.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Готовность">
            <select value={form.finish_level} onChange={(e) => patch({ finish_level: e.target.value as EstimateInput["finish_level"] })} className="w-full border border-ink/15 px-3 py-2 text-sm">
              {FINISH.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Площадь, м2">
              <input type="number" min={35} max={1200} value={form.area_m2} onChange={(e) => patch({ area_m2: Number(e.target.value) })} className="w-full border border-ink/15 px-3 py-2 text-sm" />
            </Field>
            <Field label="Этажи">
              <input type="number" min={1} max={4} value={form.floors} onChange={(e) => patch({ floors: Number(e.target.value) })} className="w-full border border-ink/15 px-3 py-2 text-sm" />
            </Field>
          </div>

          <Field label="Рельеф">
            <div className="grid grid-cols-3 gap-1">
              {(["flat", "slope", "steep"] as const).map((id) => (
                <button key={id} type="button" onClick={() => patch({ relief: id })} className={`border px-2 py-2 text-xs ${form.relief === id ? "border-pine bg-pine text-paper" : "border-ink/15 bg-white/25"}`}>
                  {id === "flat" ? "Ровный" : id === "slope" ? "Уклон" : "Склон"}
                </button>
              ))}
            </div>
          </Field>

          <div className="grid gap-2 py-3 text-sm">
            <label className="flex items-center justify-between gap-3">
              <span>9-бальная сейсмика</span>
              <input type="checkbox" checked={form.seismic} onChange={(e) => patch({ seismic: e.target.checked })} />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>Подвал/цоколь</span>
              <input type="checkbox" checked={form.basement} onChange={(e) => patch({ basement: e.target.checked })} />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>С НДС 16%</span>
              <input type="checkbox" checked={form.include_vat} onChange={(e) => patch({ include_vat: e.target.checked })} />
            </label>
          </div>

          <div className="mt-4 grid gap-3 border-t border-ink/10 pt-4">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">Сети участка</p>
            {(
              [
                ["electricity", "Электричество"],
                ["water", "Вода"],
                ["sewage", "Канализация"],
                ["gas", "Газ"],
                ["road", "Подъезд"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label}>
                <select value={form.utilities[key]} onChange={(e) => patchUtility(key, e.target.value as "connected" | "nearby" | "absent")} className="w-full border border-ink/15 px-3 py-2 text-sm">
                  {UTILITY.map(([id, title]) => (
                    <option key={id} value={id}>
                      {title}
                    </option>
                  ))}
                </select>
              </Field>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-2 border-t border-ink/10 pt-4">
            <Field label="Накл. %">
              <input type="number" min={0} max={30} value={form.overhead_pct} onChange={(e) => patch({ overhead_pct: Number(e.target.value) })} className="w-full border border-ink/15 px-2 py-2 text-sm" />
            </Field>
            <Field label="Риск %">
              <input type="number" min={0} max={25} value={form.contingency_pct} onChange={(e) => patch({ contingency_pct: Number(e.target.value) })} className="w-full border border-ink/15 px-2 py-2 text-sm" />
            </Field>
            <Field label="Приб. %">
              <input type="number" min={0} max={30} value={form.profit_pct} onChange={(e) => patch({ profit_pct: Number(e.target.value) })} className="w-full border border-ink/15 px-2 py-2 text-sm" />
            </Field>
          </div>

          {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

          <div className="mt-5 flex gap-2">
            <button type="submit" className="btn-ice inline-flex flex-1 items-center justify-center gap-2 text-sm" disabled={busy}>
              {busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
              Посчитать
            </button>
            <button type="button" onClick={() => setForm(DEFAULT_INPUT)} className="btn-ghost inline-flex items-center justify-center px-3" title="Сбросить">
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </form>

        <div className="min-w-0">
          {!result ? (
            <EmptyState onCalculate={submit} busy={busy} />
          ) : (
            <div className="grid gap-5">
              <div className="glass-strong rounded-frost p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">Итого с коэффициентами</p>
                    <p className="mt-1 text-4xl font-semibold tracking-tight text-pine">{money(result.summary.total_kzt, locale)}</p>
                    <p className="mt-1 text-sm text-ink/55">{money(result.summary.per_m2_kzt, locale)} / м2 · вилка {money(result.summary.low_kzt, locale)} - {money(result.summary.high_kzt, locale)}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={createDealInCrm}
                      className="btn-ice inline-flex items-center gap-2 text-xs font-semibold !py-2 !px-4 shadow-navy"
                    >
                      <Briefcase className="h-4 w-4 text-amber-300" />
                      <span>{dealCreated ? `В CRM (Сделка #${dealCreated})` : "Создать сделку в CRM"}</span>
                    </button>
                    <button type="button" onClick={downloadCsv} className="btn-ghost inline-flex items-center gap-2 text-xs font-semibold !py-2 !px-4">
                      <Download className="h-4 w-4" />
                      Скачать CSV
                    </button>
                  </div>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-5">
                  <Kpi label="Прямые" value={money(result.summary.direct_kzt, locale)} />
                  <Kpi label="Накладные" value={money(result.summary.overhead_kzt, locale)} />
                  <Kpi label="Риск" value={money(result.summary.contingency_kzt, locale)} />
                  <Kpi label="Прибыль" value={money(result.summary.profit_kzt, locale)} />
                  <Kpi label="НДС" value={money(result.summary.vat_kzt, locale)} />
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-[1fr_270px]">
                <div className="glass rounded-frost p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <FileSpreadsheet className="h-5 w-5 text-pine" />
                    <h2 className="font-medium">Ведомость работ и ресурсов</h2>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[760px] text-left text-sm">
                      <thead className="border-b border-ink/10 text-[11px] uppercase tracking-[0.12em] text-ink/45">
                        <tr>
                          <th className="py-2 pr-3">Код</th>
                          <th className="py-2 pr-3">Позиция</th>
                          <th className="py-2 pr-3">Кол-во</th>
                          <th className="py-2 pr-3">Цена</th>
                          <th className="py-2 text-right">Сумма</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sections.map(([section, lines]) => (
                          <Fragment key={section}>
                            <tr>
                              <td colSpan={5} className="bg-white/25 px-2 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-pine">
                                {section}
                              </td>
                            </tr>
                            {lines.map((line) => (
                              <tr key={line.code} className="border-b border-ink/10 align-top">
                                <td className="py-3 pr-3 text-ink/45">{line.code}</td>
                                <td className="py-3 pr-3">
                                  <p className="font-medium">{line.title}</p>
                                  <p className="mt-1 text-xs text-ink/45">{line.basis} · {line.confidence}</p>
                                </td>
                                <td className="py-3 pr-3">{line.qty} {line.unit}</td>
                                <td className="py-3 pr-3">{money(line.unit_price_kzt, locale)}</td>
                                <td className="py-3 text-right font-medium">{money(line.total_kzt, locale)}</td>
                              </tr>
                            ))}
                          </Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <aside className="grid h-fit gap-4">
                  <div className="glass rounded-frost p-4">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">Объемы</p>
                    <div className="mt-3 grid gap-2 text-sm">
                      {Object.entries(result.quantities).map(([key, value]) => (
                        <div key={key} className="flex justify-between gap-3 border-b border-ink/10 pb-1">
                          <span className="text-ink/55">{key.replaceAll("_", " ")}</span>
                          <span className="font-medium">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="glass rounded-frost p-4">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">Проверки</p>
                    <ul className="mt-3 grid gap-2 text-sm text-ink/65">
                      {result.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                </aside>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-[11px] uppercase tracking-[0.12em] text-ink/45">{label}</span>
      {children}
    </label>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink/10 bg-white/30 p-3">
      <p className="text-[11px] uppercase tracking-[0.12em] text-ink/45">{label}</p>
      <p className="mt-1 text-lg font-medium">{value}</p>
    </div>
  );
}

function EmptyState({ onCalculate, busy }: { onCalculate: () => void; busy: boolean }) {
  return (
    <div className="glass-strong grid min-h-[520px] place-items-center rounded-frost p-8 text-center">
      <div className="max-w-md">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-full border border-pine/20 text-pine">
          <Calculator className="h-6 w-6" />
        </div>
        <h2 className="mt-4 text-2xl font-medium">Соберем смету за пару секунд</h2>
        <p className="mt-2 text-sm leading-6 text-ink/55">
          Задайте конструктив, метраж и статус сетей. ANYQ рассчитает BOQ, покажет вилку бюджета и даст CSV для ПТО или КП подрядчика.
        </p>
        <button type="button" onClick={onCalculate} className="btn-ice mt-5 inline-flex items-center gap-2 text-sm" disabled={busy}>
          {busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
          Посчитать демо-дом
        </button>
      </div>
    </div>
  );
}
