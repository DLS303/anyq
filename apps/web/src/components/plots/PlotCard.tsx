"use client";

import Link from "next/link";
import type { Locale, Plot } from "@/lib/types";
import { PURPOSE, maskCadastral, money, titleOf } from "@/lib/format";
import { t } from "@/i18n/messages";
import { useCompare } from "@/lib/compare";
import { Check, CheckCircle2, ShieldAlert, Sparkles, ArrowRight } from "lucide-react";

export function PlotCard({ plot, locale }: { plot: Plot; locale: Locale }) {
  const m = t(locale);
  const compare = useCompare();
  const cover = plot.photos?.[0] || "/design/plot-parcel.jpg";
  const clear = plot.verified && !plot.red_lines && !plot.encumbrances;
  const isCompared = compare.has(plot.id);

  function handleCompareToggle() {
    compare.toggle(plot.id);
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("anyq-toast", {
          detail: {
            message: !isCompared
              ? `Участок "${titleOf(plot, locale)}" добавлен в сравнение`
              : `Участок удален из сравнения`,
          },
        })
      );
    }
  }

  return (
    <article className="glass-strong rounded-3xl overflow-hidden shadow-luxury hover:shadow-luxury-lg transition-all duration-300 border border-slate-200/90 group flex flex-col justify-between">
      <Link href={`/${locale}/plots/${plot.slug}`} className="block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <div className="relative overflow-hidden h-44 w-full bg-slate-100">
          <img
            src={cover}
            alt=""
            className="h-full w-full object-cover group-hover:scale-104 transition-transform duration-500"
          />
          <div className="absolute top-3 left-3">
            <span
              className={`pill text-[10px] font-bold shadow-xs ${
                clear
                  ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                  : plot.verified
                    ? "bg-amber-50 text-amber-800 border-amber-300"
                    : "bg-white/90 text-slate-600 border-slate-200"
              }`}
            >
              {clear ? (
                <>
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  <span>Верифицирован</span>
                </>
              ) : plot.red_lines ? (
                <>
                  <ShieldAlert className="h-3 w-3 text-amber-600" />
                  <span>Ограничения</span>
                </>
              ) : (
                <span>{m.unverified}</span>
              )}
            </span>
          </div>

          <div className="absolute top-3 right-3">
            <span className="pill text-[10px] bg-slate-900/80 text-white border-transparent backdrop-blur-md">
              {plot.area_sotka} сот.
            </span>
          </div>
        </div>

        <div className="p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {PURPOSE[plot.purpose][locale]} · {plot.district}
          </p>
          <h3 className="text-lg font-bold text-slate-900 group-hover:text-pine transition-colors mt-1 line-clamp-1">
            {titleOf(plot, locale)}
          </h3>
          <p className="text-xl font-bold text-pine mt-2">{money(plot.price_kzt, locale)}</p>
          <p className="font-mono text-xs text-slate-400 mt-1">
            {maskCadastral(plot.cadastral_no, plot.verified)}
          </p>
        </div>
      </Link>

      <div className="px-5 pb-5 pt-1 border-t border-slate-100 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={handleCompareToggle}
          className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all flex items-center gap-1.5 ${
            isCompared
              ? "bg-pine text-white border-pine shadow-xs"
              : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
          }`}
        >
          {isCompared ? <Check className="h-3.5 w-3.5" /> : null}
          <span>{isCompared ? "В сравнении" : m.compare}</span>
        </button>

        <Link
          href={`/${locale}/plots/${plot.slug}`}
          className="text-xs font-bold text-pine hover:underline flex items-center gap-1"
        >
          <span>Паспорт</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </article>
  );
}
