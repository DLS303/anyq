"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { fetchPlots, orderMaterial } from "@/lib/api";
import { MATERIAL_CAT, money } from "@/lib/format";
import type { Locale, Material, Plot } from "@/lib/types";
import { t } from "@/i18n/messages";

export function MaterialView({ locale, item }: { locale: Locale; item: Material }) {
  const m = t(locale);
  const { user } = useAuth();
  const [qty, setQty] = useState(String(item.min_qty));
  const [plotId, setPlotId] = useState("");
  const [address, setAddress] = useState("");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [plots, setPlots] = useState<Plot[]>([]);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetchPlots()
      .then(setPlots)
      .catch(() => setPlots([]));
  }, []);

  async function order() {
    if (!user) {
      setError(m.needLogin);
      return;
    }
    try {
      const o = await orderMaterial(user.email, {
        material_id: item.id,
        qty: Number(qty),
        plot_id: plotId || undefined,
        address,
        phone,
      });
      setDone(o.id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    }
  }

  const title = locale === "kk" ? item.title_kk : item.title_ru;
  const desc = locale === "kk" ? item.description_kk : item.description_ru;
  const amount = Number(qty || 0) * item.price_kzt;

  return (
    <div className="grid md:grid-cols-[1.1fr_0.9fr] gap-8">
      <div>
        {item.photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.photo} alt="" className="h-64 w-full object-cover border border-ink/10" />
        ) : null}
        <p className="text-[11px] uppercase tracking-wider text-ink/45 mt-4">{MATERIAL_CAT[item.category][locale]}</p>
        <h1 className="font-serif text-4xl mt-1">{title}</h1>
        <p className="mt-3 text-ink/70">{desc}</p>
        <p className="mt-4 font-serif text-3xl">
          {money(item.price_kzt, locale)} / {item.unit}
        </p>
        <p className="text-sm text-ink/50 mt-1">
          {item.city} · склад {item.stock} {item.unit}
        </p>
      </div>
      <div className="border border-ink/10 bg-white/50 p-5 h-fit">
        <h2 className="font-serif text-2xl">{m.orderMat}</h2>
        {done ? (
          <p className="mt-3 text-sm">
            {m.submitted}{" "}
            <Link href={`/${locale}/cabinet`} className="underline font-medium text-pine">
              {m.navCabinet}
            </Link>
            <span className="mx-2 text-ink/30">•</span>
            <Link href={`/${locale}/crm`} className="underline font-medium text-pine">
              {m.navCrm}
            </Link>
          </p>
        ) : (
          <div className="mt-3 grid gap-3">
            <label className="text-xs uppercase tracking-wider text-ink/50">
              {m.qty} ({item.unit}, min {item.min_qty})
              <input
                className="mt-1 w-full border border-ink/15 px-3 py-2 text-sm font-sans normal-case tracking-normal"
                type="number"
                min={item.min_qty}
                step="any"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
            </label>
            <select className="border border-ink/15 px-3 py-2 text-sm" value={plotId} onChange={(e) => setPlotId(e.target.value)}>
              <option value="">участок доставки (необяз.)</option>
              {plots.map((p) => (
                <option key={p.id} value={p.id}>
                  {locale === "kk" ? p.title_kk : p.title_ru}
                </option>
              ))}
            </select>
            <input className="border border-ink/15 px-3 py-2 text-sm" placeholder="адрес" value={address} onChange={(e) => setAddress(e.target.value)} />
            <input className="border border-ink/15 px-3 py-2 text-sm" placeholder={m.phone} value={phone} onChange={(e) => setPhone(e.target.value)} />
            <p className="text-sm">{money(Number.isFinite(amount) ? amount : 0, locale)}</p>
            <button type="button" onClick={order} className="bg-pine text-paper py-2">
              {m.order}
            </button>
            {error ? <p className="text-clay text-sm">{error}</p> : null}
            {!user ? (
              <Link href={`/${locale}/login`} className="text-sm underline">
                {m.needLogin}
              </Link>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
