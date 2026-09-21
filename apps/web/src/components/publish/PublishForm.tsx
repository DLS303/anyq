"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { createPlot, fetchPlot, submitPlot, updatePlot, uploadPhoto } from "@/lib/api";
import { PURPOSE, RELIEF, UTILITY } from "@/lib/format";
import { DISTRICTS, type Locale, type Purpose, type Relief, type Utility } from "@/lib/types";
import { t } from "@/i18n/messages";

const DrawMap = dynamic(() => import("@/components/catalog/DrawMap"), { ssr: false });

const UTILS: Utility[] = ["connected", "nearby", "tu_received", "absent"];
const RELIEFS: Relief[] = ["flat", "slope", "steep"];

type Draft = {
  cadastral_no: string;
  title_ru: string;
  title_kk: string;
  district: string;
  purpose: Purpose;
  area_sotka: string;
  price_kzt: string;
  electricity: Utility;
  gas: Utility;
  water: Utility;
  sewage: Utility;
  access_road: Utility;
  relief: Relief;
  soil: string;
  encumbrances: string;
  registered_buildings: boolean;
  red_lines: boolean;
  power_protection_zone: boolean;
  gas_protection_zone: boolean;
  water_protection: boolean;
  egrn: boolean;
  topo: boolean;
  apz: boolean;
  tu: boolean;
  description_ru: string;
  photos: string[];
};

const empty: Draft = {
  cadastral_no: "",
  title_ru: "",
  title_kk: "",
  district: "Талгарский район",
  purpose: "izhs",
  area_sotka: "",
  price_kzt: "",
  electricity: "absent",
  gas: "absent",
  water: "absent",
  sewage: "absent",
  access_road: "absent",
  relief: "flat",
  soil: "",
  encumbrances: "",
  registered_buildings: false,
  red_lines: false,
  power_protection_zone: false,
  gas_protection_zone: false,
  water_protection: false,
  egrn: false,
  topo: false,
  apz: false,
  tu: false,
  description_ru: "",
  photos: [],
};

export function PublishForm({ locale, editId }: { locale: Locale; editId?: string }) {
  const m = t(locale);
  const { user } = useAuth();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(empty);
  const [points, setPoints] = useState<[number, number][]>([]);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [needsResubmit, setNeedsResubmit] = useState(false);

  useEffect(() => {
    if (!editId || !user) return;
    fetchPlot(editId, user.email).then(({ plot }) => {
      setDraft({
        cadastral_no: plot.cadastral_no,
        title_ru: plot.title_ru,
        title_kk: plot.title_kk,
        district: plot.district,
        purpose: plot.purpose,
        area_sotka: String(plot.area_sotka),
        price_kzt: String(plot.price_kzt),
        electricity: plot.electricity,
        gas: plot.gas,
        water: plot.water,
        sewage: plot.sewage,
        access_road: plot.access_road,
        relief: plot.relief ?? "flat",
        soil: plot.soil ?? "",
        encumbrances: plot.encumbrances ?? "",
        registered_buildings: plot.registered_buildings,
        red_lines: plot.red_lines,
        power_protection_zone: plot.power_protection_zone,
        gas_protection_zone: plot.gas_protection_zone,
        water_protection: plot.water_protection,
        egrn: plot.docs?.egrn ?? false,
        topo: plot.docs?.topo ?? false,
        apz: plot.docs?.apz ?? false,
        tu: plot.docs?.tu ?? false,
        description_ru: plot.description_ru,
        photos: plot.photos ?? [],
      });
      const poly = plot.polygon as [number, number][];
      setPoints(poly.length > 1 && poly[0][0] === poly[poly.length - 1][0] ? poly.slice(0, -1) : poly);
      setNeedsResubmit(plot.status === "needs_revision" || plot.status === "draft");
    }).catch((err: Error) => setError(err.message));
  }, [editId, user]);

  if (!user || (user.role !== "owner" && user.role !== "admin")) {
    return (
      <p className="text-ink/70">
        {m.needOwner}{" "}
        <Link href={`/${locale}/login`} className="underline">
          {m.navLogin}
        </Link>
      </p>
    );
  }

  const email = user.email;
  const steps = [m.step1, m.step2, m.step3, m.step4];

  function patch<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  async function submit() {
    setBusy(true);
    setError("");
    const payload = {
      cadastral_no: draft.cadastral_no.trim(),
      title_ru: draft.title_ru,
      title_kk: draft.title_kk || draft.title_ru,
      district: draft.district,
      purpose: draft.purpose,
      area_sotka: Number(draft.area_sotka),
      price_kzt: Number(draft.price_kzt),
      electricity: draft.electricity,
      gas: draft.gas,
      water: draft.water,
      sewage: draft.sewage,
      access_road: draft.access_road,
      relief: draft.relief,
      soil: draft.soil,
      encumbrances: draft.encumbrances,
      registered_buildings: draft.registered_buildings,
      red_lines: draft.red_lines,
      power_protection_zone: draft.power_protection_zone,
      gas_protection_zone: draft.gas_protection_zone,
      water_protection: draft.water_protection,
      docs: { egrn: draft.egrn, topo: draft.topo, apz: draft.apz, tu: draft.tu },
      description_ru: draft.description_ru,
      polygon: points,
      photos: draft.photos,
    };
    try {
      let plot;
      if (editId) {
        plot = await updatePlot(email, editId, payload);
        if (needsResubmit) plot = await submitPlot(email, plot.id);
      } else {
        plot = await createPlot(email, payload);
      }
      setDone(plot.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="border border-pine p-6 bg-white/60">
        <p className="font-serif text-2xl">{m.submitted}</p>
        <Link href={`/${locale}/cabinet`} className="mt-4 inline-block underline">
          {m.navCabinet}
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-6 max-w-3xl">
      <p className="text-sm text-ink/60">{m.publishLead}</p>
      <ol className="flex gap-2 text-xs uppercase tracking-wider">
        {steps.map((label, i) => (
          <li key={label} className={`px-2 py-1 border ${i === step ? "bg-pine text-paper border-pine" : "border-ink/15"}`}>
            {i + 1}. {label}
          </li>
        ))}
      </ol>

      {step === 0 ? (
        <div className="grid gap-3">
          <Field label={m.cadastral} value={draft.cadastral_no} onChange={(v) => patch("cadastral_no", v)} placeholder="20-315-027-142" />
          <Field label="Название RU" value={draft.title_ru} onChange={(v) => patch("title_ru", v)} />
          <Field label="Атауы KK" value={draft.title_kk} onChange={(v) => patch("title_kk", v)} />
          <label className="grid gap-1 text-xs uppercase tracking-wider text-ink/50">
            {m.district}
            <select
              className="border border-ink/15 bg-white px-3 py-2 text-sm font-sans normal-case tracking-normal"
              value={draft.district}
              onChange={(e) => patch("district", e.target.value)}
            >
              {DISTRICTS.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-xs uppercase tracking-wider text-ink/50">
            {m.purpose}
            <select
              className="border border-ink/15 bg-white px-3 py-2 text-sm font-sans normal-case tracking-normal"
              value={draft.purpose}
              onChange={(e) => patch("purpose", e.target.value as Purpose)}
            >
              {(Object.keys(PURPOSE) as Purpose[]).map((p) => (
                <option key={p} value={p}>
                  {PURPOSE[p][locale]}
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <Field label={m.sotka} value={draft.area_sotka} onChange={(v) => patch("area_sotka", v)} />
            <Field label="₸" value={draft.price_kzt} onChange={(v) => patch("price_kzt", v)} />
          </div>
        </div>
      ) : null}

      {step === 1 ? (
        <div className="grid sm:grid-cols-2 gap-3">
          <Util label={m.electricity} value={draft.electricity} onChange={(v) => patch("electricity", v)} locale={locale} />
          <Util label={m.gas} value={draft.gas} onChange={(v) => patch("gas", v)} locale={locale} />
          <Util label={m.water} value={draft.water} onChange={(v) => patch("water", v)} locale={locale} />
          <Util label={m.sewage} value={draft.sewage} onChange={(v) => patch("sewage", v)} locale={locale} />
          <Util label={m.road} value={draft.access_road} onChange={(v) => patch("access_road", v)} locale={locale} />
        </div>
      ) : null}

      {step === 2 ? (
        <div className="grid gap-3">
          <label className="grid gap-1 text-xs uppercase tracking-wider text-ink/50">
            {m.relief}
            <select
              className="border border-ink/15 bg-white px-3 py-2 text-sm font-sans normal-case tracking-normal"
              value={draft.relief}
              onChange={(e) => patch("relief", e.target.value as Relief)}
            >
              {RELIEFS.map((r) => (
                <option key={r} value={r}>
                  {RELIEF[r][locale]}
                </option>
              ))}
            </select>
          </label>
          <Field label={m.soil} value={draft.soil} onChange={(v) => patch("soil", v)} />
          <Field label={m.encumbrances} value={draft.encumbrances} onChange={(v) => patch("encumbrances", v)} />
          <Check label={m.buildings} checked={draft.registered_buildings} onChange={(v) => patch("registered_buildings", v)} />
          <Check label={m.redLines} checked={draft.red_lines} onChange={(v) => patch("red_lines", v)} />
          <Check label={m.powerZone} checked={draft.power_protection_zone} onChange={(v) => patch("power_protection_zone", v)} />
          <Check label={m.gasZone} checked={draft.gas_protection_zone} onChange={(v) => patch("gas_protection_zone", v)} />
          <Check label={m.waterZone} checked={draft.water_protection} onChange={(v) => patch("water_protection", v)} />
          <Check label={m.docEgrn} checked={draft.egrn} onChange={(v) => patch("egrn", v)} />
          <Check label={m.docTopo} checked={draft.topo} onChange={(v) => patch("topo", v)} />
          <Check label={m.docApz} checked={draft.apz} onChange={(v) => patch("apz", v)} />
          <Check label={m.docTu} checked={draft.tu} onChange={(v) => patch("tu", v)} />
          <label className="grid gap-1 text-xs uppercase tracking-wider text-ink/50">
            описание
            <textarea
              className="border border-ink/15 bg-white px-3 py-2 text-sm font-sans normal-case tracking-normal"
              rows={3}
              value={draft.description_ru}
              onChange={(e) => patch("description_ru", e.target.value)}
            />
          </label>
          <p className="text-xs uppercase tracking-wider text-ink/50">{m.photos}</p>
          <div className="flex flex-wrap gap-2">
            {draft.photos.map((src) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={src} src={src} alt="" className="h-20 w-28 object-cover border border-ink/10" />
            ))}
          </div>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              try {
                const url = await uploadPhoto(email, file);
                setDraft((d) => ({ ...d, photos: [...d.photos, url] }));
              } catch (err) {
                setError(err instanceof Error ? err.message : "upload");
              }
            }}
          />
        </div>
      ) : null}

      {step === 3 ? (
        <div>
          <p className="text-sm text-ink/60 mb-2">{m.drawHint}</p>
          <div className="h-[360px] border border-ink/10 overflow-hidden">
            <DrawMap points={points} onAdd={(pt) => setPoints((p) => [...p, pt])} />
          </div>
          <div className="mt-2 flex gap-3 text-sm">
            <button type="button" onClick={() => setPoints((p) => p.slice(0, -1))} className="underline">
              {m.undo}
            </button>
            <button type="button" onClick={() => setPoints([])} className="underline">
              {m.clear}
            </button>
            <span className="text-ink/45">{points.length} pts</span>
          </div>
        </div>
      ) : null}

      {error ? <p className="text-clay text-sm">{error}</p> : null}
      <div className="flex gap-3">
        {step > 0 ? (
          <button type="button" className="border border-ink/20 px-4 py-2" onClick={() => setStep((s) => s - 1)}>
            {m.back}
          </button>
        ) : null}
        {step < 3 ? (
          <button type="button" className="bg-pine text-paper px-4 py-2" onClick={() => setStep((s) => s + 1)}>
            {m.next}
          </button>
        ) : (
          <button type="button" disabled={busy} className="bg-pine text-paper px-4 py-2 disabled:opacity-50" onClick={submit}>
            {m.submit}
          </button>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-xs uppercase tracking-wider text-ink/50">{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="border border-ink/15 bg-white px-3 py-2"
      />
    </label>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function Util({
  label,
  value,
  onChange,
  locale,
}: {
  label: string;
  value: Utility;
  onChange: (v: Utility) => void;
  locale: Locale;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-xs uppercase tracking-wider text-ink/50">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as Utility)}
        className="border border-ink/15 bg-white px-3 py-2 text-sm"
      >
        {UTILS.map((u) => (
          <option key={u} value={u}>
            {UTILITY[u][locale]}
          </option>
        ))}
      </select>
    </label>
  );
}
