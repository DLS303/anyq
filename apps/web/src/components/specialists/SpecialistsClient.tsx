"use client";

import Link from "next/link";
import { memo, useState } from "react";
import { PhotoView } from "@/components/media/PhotoView";
import { PageNav, usePaged } from "@/components/ui/PagedList";
import { fetchSpecialists } from "@/lib/api";
import { ErrorRetry, LoadingSkeleton, useAsync } from "@/lib/useAsync";
import { CATEGORY, money, ratingLabel, reviewsLabel } from "@/lib/format";
import type { Locale, SpecCategory, Specialist } from "@/lib/types";
import { t } from "@/i18n/messages";
import { CheckCircle2, ShieldCheck, Star } from "lucide-react";

const CATS: SpecCategory[] = ["survey", "legal", "architecture", "smr", "supervision", "equipment"];

export function SpecialistsClient({ locale }: { locale: Locale }) {
  const m = t(locale);
  const [category, setCategory] = useState("");
  const query = useAsync((signal) => fetchSpecialists({ category: category || undefined }, signal), [category]);
  const items = query.data ?? [];
  const paged = usePaged(items, category);

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

      {query.loading ? <LoadingSkeleton label={m.hubLoading} /> : null}
      {query.status === "error" ? (
        <ErrorRetry message={m.listLoadError} retryLabel={m.retry} onRetry={query.reload} />
      ) : null}
      {query.status !== "error" && paged.slice.length > 0 ? (
      <div className="grid gap-5 sm:grid-cols-2">
        {paged.slice.map((s) => (
          <SpecialistCard key={s.id} specialist={s} locale={locale} />
        ))}
      </div>
      ) : null}
      <PageNav
        page={paged.page}
        pages={paged.pages}
        status={m.pageStatus.replace("{page}", String(paged.page + 1)).replace("{pages}", String(paged.pages))}
        prevLabel={m.pagePrev}
        nextLabel={m.pageNext}
        onPage={paged.setPage}
      />

      {!query.loading && query.status !== "error" && items.length === 0 ? (
        <div className="py-12 text-center text-sm text-slate-400">
          В выбранной категории специалистов не найдено.
        </div>
      ) : null}
    </div>
  );
}

const SpecialistCard = memo(function SpecialistCard({
  specialist: s,
  locale,
}: {
  specialist: Specialist;
  locale: Locale;
}) {
  return (
          <div
            className="glass-strong flex flex-col justify-between overflow-hidden rounded-3xl border border-slate-200/90 shadow-luxury transition-all duration-300 group hover:shadow-luxury-lg"
          >
            <Link href={`/${locale}/specialists/${s.slug}`} className="block">
              {s.cover ? (
                <PhotoView
                  src={s.cover}
                  alt=""
                  sizes="(max-width: 640px) 100vw, 50vw"
                  className="h-48 w-full object-cover transition-transform duration-500 group-hover:scale-102"
                />
              ) : null}
              <div className="p-6">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="pill text-[10px] text-slate-600 font-semibold">{CATEGORY[s.category][locale]}</span>
                  <span className="flex items-center gap-1 text-xs font-bold text-amber-600">
                    <Star className="h-3.5 w-3.5 fill-amber-500 text-amber-500" />
                    <span>{ratingLabel(s.rating, s.reviews_count)}</span>
                  </span>
                </div>

                <h3 className="text-xl font-bold text-slate-900 group-hover:text-pine transition-colors">
                  {locale === "kk" ? s.company_kk : s.company_ru}
                </h3>

                <p className="text-xs text-slate-500 mt-1 font-medium">
                  {s.city} · {reviewsLabel(s.reviews_count)}
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
  );
});
