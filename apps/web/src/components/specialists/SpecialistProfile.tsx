"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { createOrder, fetchPlots } from "@/lib/api";
import { CATEGORY, money, titleOf } from "@/lib/format";
import type { Locale, Plot, Review, Specialist } from "@/lib/types";
import { t } from "@/i18n/messages";

export function SpecialistProfile({
  locale,
  specialist,
  reviews,
}: {
  locale: Locale;
  specialist: Specialist;
  reviews: Review[];
}) {
  const m = t(locale);
  const { user } = useAuth();
  const [plots, setPlots] = useState<Plot[]>([]);
  const [plotId, setPlotId] = useState("");
  const [message, setMessage] = useState("");
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
      const o = await createOrder(user.email, specialist.id, { plot_id: plotId || undefined, message });
      setDone(o.thread_id || o.id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    }
  }

  const name = locale === "kk" ? specialist.company_kk : specialist.company_ru;
  const bio = locale === "kk" ? specialist.bio_kk : specialist.bio_ru;

  return (
    <div className="grid gap-8">
      <div className="grid md:grid-cols-[1.1fr_0.9fr] gap-6">
        <div>
          {specialist.cover ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={specialist.cover} alt="" className="h-56 w-full object-cover border border-ink/10" />
          ) : null}
          <p className="text-[11px] uppercase tracking-wider text-ink/45 mt-4">{CATEGORY[specialist.category][locale]}</p>
          <h1 className="font-serif text-4xl mt-1">{name}</h1>
          <p className="mt-3 text-ink/70">{bio}</p>
          <p className="mt-3 text-sm">
            ★ {specialist.rating || "—"} · {specialist.reviews_count} · {specialist.city}
            {specialist.license_verified ? ` · ${m.license} ${specialist.license_cat} ${specialist.license_no}` : ""}
          </p>
          {specialist.bin ? <p className="text-xs text-ink/45 mt-1">БИН {specialist.bin}</p> : null}
        </div>
        <div className="border border-ink/10 bg-white/50 p-5">
          <h2 className="font-serif text-2xl">{m.order}</h2>
          {done ? (
            <p className="mt-3 text-sm">
              {m.ordered}{" "}
              <Link href={`/${locale}/chat/${done}`} className="underline font-medium text-pine">
                {m.navChat}
              </Link>
              <span className="mx-2 text-ink/30">•</span>
              <Link href={`/${locale}/crm`} className="underline font-medium text-pine">
                {m.navCrm}
              </Link>
            </p>
          ) : (
            <div className="mt-3 grid gap-3">
              <select
                className="border border-ink/15 px-3 py-2 text-sm"
                value={plotId}
                onChange={(e) => setPlotId(e.target.value)}
              >
                <option value="">участок (необязательно)</option>
                {plots.map((p) => (
                  <option key={p.id} value={p.id}>
                    {titleOf(p, locale)}
                  </option>
                ))}
              </select>
              <textarea
                className="border border-ink/15 px-3 py-2 text-sm"
                rows={3}
                placeholder={m.message}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
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

      <section>
        <h2 className="font-serif text-2xl mb-3">{m.prices}</h2>
        <div className="grid gap-2">
          {specialist.prices.map((p) => (
            <div key={p.title_ru} className="flex justify-between border border-ink/10 p-3 text-sm">
              <span>
                {locale === "kk" ? p.title_kk : p.title_ru} · {p.unit}
              </span>
              <span>{money(p.price_kzt, locale)}</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="font-serif text-2xl mb-3">{m.portfolio}</h2>
        <div className="grid sm:grid-cols-2 gap-3">
          {specialist.portfolio.map((p) => (
            <Link
              key={p.title_ru}
              href={p.plot_id ? `/${locale}/plots/${p.plot_id}` : "#"}
              className="border border-ink/10"
            >
              {p.photo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={p.photo} alt="" className="h-32 w-full object-cover" />
              ) : null}
              <p className="p-3 text-sm">{p.title_ru}</p>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="font-serif text-2xl mb-3">{m.reviews}</h2>
        {reviews.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
        <div className="grid gap-3">
          {reviews.map((r) => (
            <div key={r.id} className="border border-ink/10 p-4">
              <p>{"★".repeat(r.stars)}</p>
              <p className="text-sm mt-1">{r.text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
