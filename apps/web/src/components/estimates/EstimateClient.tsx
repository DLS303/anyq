"use client";

import { Fragment, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Calculator, Download, FileSpreadsheet, RefreshCw, Briefcase, CheckCircle2 } from "lucide-react";
import { calculateEstimate, createDeal } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { features } from "@/lib/features";
import { registerHref } from "@/lib/registration";
import { money } from "@/lib/format";
import type { EstimateInput, EstimateResult, Locale } from "@/lib/types";

function estCopy(locale: Locale) {
  const kk = locale === "kk";
  return {
    kicker: kk ? "Алдын ала смета · коэффициент" : "Предварительный бюджет · коэффициенты",
    title: kk ? "Алдын ала смета" : "Предварительный бюджет",
    lead: kk
      ? "Үй, жер телімі және сыртқы желілер бойынша алдын ала қаржы. Есеп коэффициентпен жүреді, нормативтік база емес."
      : "Предварительный бюджет по дому, участку и наружным сетям. Расчёт по коэффициентам, без нормативной базы.",
    region: kk ? "Өңір" : "Регион",
    area: kk ? "Аудан" : "Площадь",
    baseDate: kk ? "База күні" : "Дата базы",
    params: kk ? "Параметрлер" : "Параметры",
    construct: kk ? "Құрылым" : "Конструктив",
    finish: kk ? "Дайындық" : "Готовность",
    areaM2: kk ? "Аудан, м2" : "Площадь, м2",
    floors: kk ? "Қабат" : "Этажи",
    relief: kk ? "Бедер" : "Рельеф",
    flat: kk ? "Тегіс" : "Ровный",
    slope: kk ? "Еңіс" : "Уклон",
    steep: kk ? "Қия" : "Склон",
    seismic: kk ? "9 балдық сейсмика" : "9-бальная сейсмика",
    basement: kk ? "Жертөле" : "Подвал/цоколь",
    vat: kk ? "ҚҚС 16%" : "С НДС 16%",
    networks: kk ? "Жер телімінің желілері" : "Сети участка",
    electricity: kk ? "Электр" : "Электричество",
    water: kk ? "Су" : "Вода",
    sewage: kk ? "Кәріз" : "Канализация",
    gas: kk ? "Газ желісі" : "Газ",
    road: kk ? "Кіреберіс" : "Подъезд",
    connected: kk ? "Қосылған" : "Подключено",
    nearby: kk ? "Жақын" : "Рядом",
    absent: kk ? "Жоқ" : "Нет",
    overhead: kk ? "Үстеме %" : "Накл. %",
    risk: kk ? "Тәуекел %" : "Риск %",
    profit: kk ? "Пайда %" : "Приб. %",
    calc: kk ? "Есептеу" : "Посчитать",
    reset: kk ? "Тазалау" : "Сбросить",
    demoHouse: kk ? "Демо-үйді есептеу" : "Посчитать демо-дом",
    emptyTitle: kk ? "Параметрлерді толтырыңыз" : "Заполните параметры",
    emptyLead: kk
      ? "Құрылымды, ауданды және желілерді көрсетіңіз. Нәтиже коэффициентпен шығады."
      : "Задайте конструктив, метраж и сети. Итог считается по коэффициентам.",
    total: kk ? "Коэффициентпен жиыны" : "Итого с коэффициентами",
    range: kk ? "аралық" : "вилка",
    deal: kk ? "Келісім жасау" : "Создать сделку",
    csv: kk ? "CSV жүктеу" : "Скачать CSV",
    direct: kk ? "Тікелей" : "Прямые",
    overheadSum: kk ? "Үстеме" : "Накладные",
    riskSum: kk ? "Тәуекел" : "Риск",
    profitSum: kk ? "Пайда" : "Прибыль",
    vatSum: kk ? "ҚҚС" : "НДС",
    sheet: kk ? "Жұмыс пен ресурс тізімі" : "Ведомость работ и ресурсов",
    code: kk ? "Шифр" : "Код",
    pos: kk ? "Тармақ" : "Позиция",
    qty: kk ? "Саны" : "Кол-во",
    price: kk ? "Баға" : "Цена",
    sum: kk ? "Сома" : "Сумма",
    volumes: kk ? "Көлемдер" : "Объёмы",
    checks: kk ? "Тексерулер" : "Проверки",
    fail: kk ? "Смета есептелмеді" : "Не удалось посчитать смету",
    needLogin: kk ? "Алдымен кіріңіз" : "Сначала войдите",
    regions: [
      ["almaty", "Алматы"],
      ["astana", "Астана"],
      ["shymkent", "Шымкент"],
      ["west", kk ? "Батыс" : "Запад РК"],
      ["north", kk ? "Солтүстік" : "Север/центр"],
      ["other", kk ? "Басқа өңір" : "Другой регион"],
    ] as const,
    houses: [
      ["gasblock", kk ? "Газблок" : "Газоблок"],
      ["brick", kk ? "Кірпіш" : "Кирпич"],
      ["monolith", kk ? "Монолитті" : "Монолит"],
      ["frame", kk ? "Қаңқа" : "Каркас"],
      ["sip", "СИП"],
    ] as const,
    finishes: [
      ["shell", kk ? "Қаралай" : "Черновой"],
      ["prefinish", kk ? "Алдын ала әрлеу" : "Предчистовой"],
      ["turnkey", kk ? "Таза әрлеу" : "Чистовой"],
    ] as const,
  };
}

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
  const L = estCopy(locale);
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
            detail: { message: L.needLogin },
          }),
        );
        router.push(registerHref(locale));
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
      setError(e instanceof Error ? e.message : L.fail);
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
          <p className="text-[11px] uppercase tracking-[0.16em] text-ink/45">{L.kicker}</p>
          {embedded ? (
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{L.title}</h2>
          ) : (
            <h1 className="mt-2 text-4xl font-medium tracking-tight">{L.title}</h1>
          )}
          <p className="mt-3 max-w-2xl text-[15px] leading-6 text-ink/60">{L.lead}</p>
        </div>
        <div className={`grid gap-3 ${features.estimateBaseDate ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
          <Kpi label={L.region} value={L.regions.find(([id]) => id === form.region)?.[1] || "РК"} />
          <Kpi label={L.area} value={`${form.area_m2} м2`} />
          {features.estimateBaseDate ? <Kpi label={L.baseDate} value="09.2026" /> : null}
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
            <h2 className="text-lg font-medium">{L.params}</h2>
          </div>

          <Field label={L.region}>
            <select value={form.region} onChange={(e) => patch({ region: e.target.value as EstimateInput["region"] })} className="w-full border border-ink/15 px-3 py-2 text-sm">
              {L.regions.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>

          <Field label={L.construct}>
            <select value={form.house_type} onChange={(e) => patch({ house_type: e.target.value as EstimateInput["house_type"] })} className="w-full border border-ink/15 px-3 py-2 text-sm">
              {L.houses.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>

          <Field label={L.finish}>
            <select value={form.finish_level} onChange={(e) => patch({ finish_level: e.target.value as EstimateInput["finish_level"] })} className="w-full border border-ink/15 px-3 py-2 text-sm">
              {L.finishes.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label={L.areaM2}>
              <input type="number" min={35} max={1200} value={form.area_m2} onChange={(e) => patch({ area_m2: Number(e.target.value) })} className="w-full border border-ink/15 px-3 py-2 text-sm" />
            </Field>
            <Field label={L.floors}>
              <input type="number" min={1} max={4} value={form.floors} onChange={(e) => patch({ floors: Number(e.target.value) })} className="w-full border border-ink/15 px-3 py-2 text-sm" />
            </Field>
          </div>

          <Field label={L.relief}>
            <div className="grid grid-cols-3 gap-1">
              {(["flat", "slope", "steep"] as const).map((id) => (
                <button key={id} type="button" onClick={() => patch({ relief: id })} className={`border px-2 py-2 text-xs ${form.relief === id ? "border-pine bg-pine text-paper" : "border-ink/15 bg-white/25"}`}>
                  {id === "flat" ? L.flat : id === "slope" ? L.slope : L.steep}
                </button>
              ))}
            </div>
          </Field>

          <div className="grid gap-2 py-3 text-sm">
            <label className="flex items-center justify-between gap-3">
              <span>{L.seismic}</span>
              <input type="checkbox" checked={form.seismic} onChange={(e) => patch({ seismic: e.target.checked })} />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>{L.basement}</span>
              <input type="checkbox" checked={form.basement} onChange={(e) => patch({ basement: e.target.checked })} />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>{L.vat}</span>
              <input type="checkbox" checked={form.include_vat} onChange={(e) => patch({ include_vat: e.target.checked })} />
            </label>
          </div>

          <div className="mt-4 grid gap-3 border-t border-ink/10 pt-4">
            <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">{L.networks}</p>
            {(
              [
                ["electricity", L.electricity],
                ["water", L.water],
                ["sewage", L.sewage],
                ["gas", L.gas],
                ["road", L.road],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label}>
                <select value={form.utilities[key]} onChange={(e) => patchUtility(key, e.target.value as "connected" | "nearby" | "absent")} className="w-full border border-ink/15 px-3 py-2 text-sm">
                  {([
                    ["connected", L.connected],
                    ["nearby", L.nearby],
                    ["absent", L.absent],
                  ] as const).map(([id, title]) => (
                    <option key={id} value={id}>
                      {title}
                    </option>
                  ))}
                </select>
              </Field>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-2 border-t border-ink/10 pt-4">
            <Field label={L.overhead}>
              <input type="number" min={0} max={30} value={form.overhead_pct} onChange={(e) => patch({ overhead_pct: Number(e.target.value) })} className="w-full border border-ink/15 px-2 py-2 text-sm" />
            </Field>
            <Field label={L.risk}>
              <input type="number" min={0} max={25} value={form.contingency_pct} onChange={(e) => patch({ contingency_pct: Number(e.target.value) })} className="w-full border border-ink/15 px-2 py-2 text-sm" />
            </Field>
            <Field label={L.profit}>
              <input type="number" min={0} max={30} value={form.profit_pct} onChange={(e) => patch({ profit_pct: Number(e.target.value) })} className="w-full border border-ink/15 px-2 py-2 text-sm" />
            </Field>
          </div>

          {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

          <div className="mt-5 flex gap-2">
            <button type="submit" className="btn-ice inline-flex flex-1 items-center justify-center gap-2 text-sm" disabled={busy}>
              {busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
              {L.calc}
            </button>
            <button type="button" onClick={() => setForm(DEFAULT_INPUT)} className="btn-ghost inline-flex items-center justify-center px-3" title={L.reset}>
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </form>

        <div className="min-w-0">
          {!result ? (
            <EmptyState onCalculate={submit} busy={busy} title={L.emptyTitle} lead={L.emptyLead} demoLabel={L.demoHouse} showDemo={features.demoHouse} />
          ) : (
            <div className="grid gap-5">
              <div className="glass-strong rounded-frost p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">{L.total}</p>
                    <p className="mt-1 text-4xl font-semibold tracking-tight text-pine">{money(result.summary.total_kzt, locale)}</p>
                    <p className="mt-1 text-sm text-ink/55">{money(result.summary.per_m2_kzt, locale)} / м2 · {L.range} {money(result.summary.low_kzt, locale)} - {money(result.summary.high_kzt, locale)}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={createDealInCrm}
                      className="btn-ice inline-flex items-center gap-2 text-xs font-semibold !py-2 !px-4 shadow-navy"
                    >
                      <Briefcase className="h-4 w-4 text-amber-300" />
                      <span>{dealCreated ? `${L.deal} #${dealCreated}` : L.deal}</span>
                    </button>
                    <button type="button" onClick={downloadCsv} className="btn-ghost inline-flex items-center gap-2 text-xs font-semibold !py-2 !px-4">
                      <Download className="h-4 w-4" />
                      {L.csv}
                    </button>
                  </div>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-5">
                  <Kpi label={L.direct} value={money(result.summary.direct_kzt, locale)} />
                  <Kpi label={L.overheadSum} value={money(result.summary.overhead_kzt, locale)} />
                  <Kpi label={L.riskSum} value={money(result.summary.contingency_kzt, locale)} />
                  <Kpi label={L.profitSum} value={money(result.summary.profit_kzt, locale)} />
                  <Kpi label={L.vatSum} value={money(result.summary.vat_kzt, locale)} />
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-[1fr_270px]">
                <div className="glass rounded-frost p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <FileSpreadsheet className="h-5 w-5 text-pine" />
                    <h2 className="font-medium">{L.sheet}</h2>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[760px] text-left text-sm">
                      <thead className="border-b border-ink/10 text-[11px] uppercase tracking-[0.12em] text-ink/45">
                        <tr>
                          <th className="py-2 pr-3">{L.code}</th>
                          <th className="py-2 pr-3">{L.pos}</th>
                          <th className="py-2 pr-3">{L.qty}</th>
                          <th className="py-2 pr-3">{L.price}</th>
                          <th className="py-2 text-right">{L.sum}</th>
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
                    <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">{L.volumes}</p>
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
                    <p className="text-[11px] uppercase tracking-[0.14em] text-ink/45">{L.checks}</p>
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

function EmptyState({
  onCalculate,
  busy,
  title,
  lead,
  demoLabel,
  showDemo,
}: {
  onCalculate: () => void;
  busy: boolean;
  title: string;
  lead: string;
  demoLabel: string;
  showDemo: boolean;
}) {
  return (
    <div className="glass-strong grid min-h-[520px] place-items-center rounded-frost p-8 text-center">
      <div className="max-w-md">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-full border border-pine/20 text-pine">
          <Calculator className="h-6 w-6" />
        </div>
        <h2 className="mt-4 text-2xl font-medium">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-ink/55">{lead}</p>
        {showDemo ? (
          <button type="button" onClick={onCalculate} className="btn-ice mt-5 inline-flex items-center gap-2 text-sm" disabled={busy}>
            {busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
            {demoLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
