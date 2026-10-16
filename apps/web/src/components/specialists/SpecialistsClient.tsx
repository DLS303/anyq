"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchSpecialists } from "@/lib/api";
import { CATEGORY, money } from "@/lib/format";
import type { Locale, SpecCategory, Specialist } from "@/lib/types";
import { t } from "@/i18n/messages";
import { CheckCircle2, HardHat, ShieldCheck, Star, ArrowRight } from "lucide-react";

const CATS: SpecCategory[] = ["survey", "legal", "architecture", "smr", "supervision", "equipment"];

export function SpecialistsClient({ locale }: { locale: Locale }) {
  const m = t(locale);
  const [category, setCategory] = useState("");
  const [items, setItems] = useState<Specialist[]>([]);

  useEffect(() => {
    fetchSpecialists({ category: category || undefined }).then(setItems).catch(() => setItems([]));
  }, [category]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-wider text-pine font-bold flex items-center gap-1.5 mb-1">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            <span>Аккредитованный реестр девелопмента РК</span>
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            Специалисты, архитекторы и генподрядчики
          </h1>
          <p className="mt-2 text-sm text-slate-500 leading-relaxed">
            {m.specialistsLead}
          </p>
        </div>

        {/* Filter Pills */}
        <div className="mt-6 flex flex-wrap gap-1.5 pt-4 border-t border-slate-100">
          <button
            type="button"
            onClick={() => setCategory("")}
            className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
              !category
                ? "bg-pine text-white shadow-xs"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {m.any}
          </button>
          {CATS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
                category === c
                  ? "bg-pine text-white shadow-xs"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {CATEGORY[c][locale]}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="grid sm:grid-cols-2 gap-5">
        {items.map((s) => (
          <div
            key={s.id}
            className="glass-strong rounded-3xl overflow-hidden shadow-luxury hover:shadow-luxury-lg transition-all duration-300 border border-slate-200/90 group flex flex-col justify-between"
          >
            <Link href={`/${locale}/specialists/${s.slug}`} className="block">
              {s.cover ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={s.cover}
                  alt=""
                  className="h-48 w-full object-cover group-hover:scale-102 transition-transform duration-500"
                />
              ) : null}
              <div className="p-6">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="pill text-[10px] text-slate-600 font-semibold">{CATEGORY[s.category][locale]}</span>
                  <span className="flex items-center gap-1 text-xs font-bold text-amber-600">
                    <Star className="h-3.5 w-3.5 fill-amber-500 text-amber-500" />
                    <span>{s.rating || "5.0"}</span>
                  </span>
                </div>

                <h3 className="text-xl font-bold text-slate-900 group-hover:text-pine transition-colors">
                  {locale === "kk" ? s.company_kk : s.company_ru}
                </h3>

                <p className="text-xs text-slate-500 mt-1 font-medium">
                  {s.city} · {s.reviews_count} завершенных проектов
                </p>

                {s.license_verified ? (
                  <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-800 text-[11px] font-semibold border border-emerald-200/60">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    <span>Лицензия ГАСК: {s.license_cat} категория</span>
                  </div>
                ) : null}

                {s.prices[0] ? (
                  <p className="text-sm font-semibold text-pine mt-3">
                    {locale === "kk" ? s.prices[0].title_kk : s.prices[0].title_ru} ·{" "}
                    {money(s.prices[0].price_kzt, locale)}
                  </p>
                ) : null}
              </div>
            </Link>

            <div className="px-6 pb-6 pt-1 border-t border-slate-100 flex items-center gap-2">
              <Link
                href={`/${locale}/specialists/${s.slug}`}
                className="btn-ice flex-1 text-xs font-bold !py-2.5 text-center shadow-navy"
              >
                Заказать услугу
              </Link>
              <Link
                href={`/${locale}/specialists/${s.slug}`}
                className="btn-ghost text-xs font-semibold !py-2.5 !px-3"
              >
                Профиль
              </Link>
            </div>
          </div>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="text-center py-12 text-slate-400 text-sm">
          В выбранной категории специалистов не найдено.
        </div>
      ) : null}
    </div>
  );
}
