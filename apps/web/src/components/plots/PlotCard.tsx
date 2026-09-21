"use client";

import Link from "next/link";
import type { Locale, Plot } from "@/lib/types";
import { PURPOSE, maskCadastral, money, titleOf } from "@/lib/format";
import { t } from "@/i18n/messages";
import { useCompare } from "@/lib/compare";

export function PlotCard({ plot, locale }: { plot: Plot; locale: Locale }) {
  const m = t(locale);
  const compare = useCompare();
  const cover = plot.photos?.[0] || "/design/plot-parcel.jpg";
  const clear = plot.verified && !plot.red_lines && !plot.encumbrances;
  return (
    <article className="glass-strong rounded-frost overflow-hidden transition-transform duration-[420ms] hover:-translate-y-0.5 active:scale-[0.98]">
      <Link href={`/${locale}/plots/${plot.slug}`} className="block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={cover} alt="" className="h-40 w-full object-cover" />
        <div className="p-4">
          <span className="pill">
            <span className={`inline-block h-2 w-2 rounded-full ${clear ? "bg-pine-2" : plot.verified ? "bg-clay" : "bg-ink/30"}`} />
            {clear ? m.verified : plot.red_lines ? "ограничения" : m.unverified}
          </span>
          <p className="text-[12px] tracking-wide text-ink/45 mt-3">
            {PURPOSE[plot.purpose][locale]} · {plot.district}
          </p>
          <h3 className="text-lg font-medium mt-1">{titleOf(plot, locale)}</h3>
          <p className="mt-2 font-medium">{money(plot.price_kzt, locale)}</p>
          <p className="font-mono text-[13px] text-ink/50 mt-1">
            {maskCadastral(plot.cadastral_no, plot.verified)}
          </p>
        </div>
      </Link>
      <div className="px-4 pb-4">
        <button
          type="button"
          onClick={() => compare.toggle(plot.id)}
          className={`text-xs tracking-wide ${compare.has(plot.id) ? "text-pine font-medium" : "text-ink/40"}`}
        >
          {m.compare}
        </button>
      </div>
    </article>
  );
}
