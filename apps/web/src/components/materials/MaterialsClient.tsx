"use client";

import Link from "next/link";
import { useState } from "react";
import { fetchMaterials } from "@/lib/api";
import { ErrorRetry, LoadingSkeleton, useAsync } from "@/lib/useAsync";
import { MATERIAL_CAT, money } from "@/lib/format";
import type { Locale, MaterialCat } from "@/lib/types";
import { t } from "@/i18n/messages";
import { CheckCircle2, Layers, Search, Truck, ArrowRight, X } from "lucide-react";

const CATS: MaterialCat[] = ["inert", "brick", "mix", "metal", "roofing", "lumber", "concrete"];

export function MaterialsClient({ locale }: { locale: Locale }) {
  const m = t(locale);
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const query = useAsync(
    () => fetchMaterials({ category: category || undefined, q: q || undefined }),
    [category, q],
  );
  const items = query.data ?? [];

  return (
    <div className="space-y-6">
      {/* Header and Search */}
      <div className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-wider text-pine font-bold flex items-center gap-1.5 mb-1">
            <Truck className="h-4 w-4" />
            <span>Прямые поставки от заводов-изготовителей</span>
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            Каталог строительных материалов
          </h1>
          <p className="mt-2 text-sm text-slate-500 leading-relaxed">
            Сертифицированные стройматериалы в Казахстане по оптовым ценам: бетон, газоблоки, кирпич, арматура, пиломатериалы.
          </p>
        </div>

        {/* Search Bar */}
        <div className="mt-6 relative max-w-xl">
          <Search className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Поиск по названию (напр. Бетон, Газоблок, Арматура А500С)..."
            className="w-full pl-10 pr-10 py-2.5 text-sm rounded-xl border border-slate-200 bg-white text-slate-900 shadow-2xs focus:border-pine"
          />
          {q ? (
            <button
              type="button"
              onClick={() => setQ("")}
              className="absolute right-3 top-3 text-slate-400 hover:text-slate-600"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        {/* Filter Pills */}
        <div className="mt-5 flex flex-wrap gap-1.5 pt-4 border-t border-slate-100">
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
              {MATERIAL_CAT[c][locale]}
            </button>
          ))}
        </div>
      </div>

      {query.loading ? <LoadingSkeleton label={m.hubLoading} /> : null}
      {query.status === "error" ? (
        <ErrorRetry message={m.listLoadError} retryLabel={m.hubRetry} onRetry={query.reload} />
      ) : null}
      {/* Materials Grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {items.map((item) => (
          <div
            key={item.id}
            className="glass-strong rounded-3xl overflow-hidden shadow-luxury hover:shadow-luxury-lg transition-all duration-300 border border-slate-200/90 group flex flex-col justify-between"
          >
            <Link href={`/${locale}/materials/${item.slug}`} className="block">
              {item.photo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={item.photo}
                  alt=""
                  className="h-48 w-full object-cover group-hover:scale-103 transition-transform duration-500"
                />
              ) : (
                <div className="h-48 bg-slate-100 grid place-items-center text-slate-300">
                  <Layers className="h-10 w-10 opacity-30" />
                </div>
              )}
              <div className="p-5">
                <span className="pill text-[10px] text-slate-600 font-semibold">{MATERIAL_CAT[item.category][locale]}</span>
                <h3 className="text-xl font-bold text-slate-900 group-hover:text-pine transition-colors mt-2 line-clamp-1">
                  {locale === "kk" ? item.title_kk : item.title_ru}
                </h3>
                <p className="text-2xl font-extrabold text-pine mt-2">
                  {money(item.price_kzt, locale)}{" "}
                  <span className="text-xs font-normal text-slate-500">/ {item.unit}</span>
                </p>
                <p className="text-xs text-slate-500 mt-1 font-medium">
                  {item.city} · мин. партия {item.min_qty} {item.unit} · склад {item.stock} {item.unit}
                </p>
              </div>
            </Link>

            <div className="px-5 pb-5 pt-1 border-t border-slate-100 flex items-center gap-2">
              <Link
                href={`/${locale}/materials/${item.slug}`}
                className="btn-ice flex-1 text-xs font-bold !py-2.5 text-center shadow-navy"
              >
                Заказать на объект
              </Link>
              <Link
                href={`/${locale}/materials/${item.slug}`}
                className="btn-ghost text-xs font-semibold !py-2.5 !px-3"
              >
                Детали
              </Link>
            </div>
          </div>
        ))}
      </div>

      {!query.loading && query.status !== "error" && items.length === 0 ? (
        <div className="text-center py-12 text-slate-400 text-sm">
          По вашему запросу ничего не найдено. Попробуйте сбросить фильтры.
        </div>
      ) : null}
    </div>
  );
}
