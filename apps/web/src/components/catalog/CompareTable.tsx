"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchPlot } from "@/lib/api";
import { PURPOSE, RELIEF, UTILITY, money, titleOf } from "@/lib/format";
import type { Locale, Plot } from "@/lib/types";
import { t } from "@/i18n/messages";

export function CompareTable({ locale, ids }: { locale: Locale; ids: string[] }) {
  const m = t(locale);
  const [plots, setPlots] = useState<Plot[]>([]);

  useEffect(() => {
    Promise.all(ids.map((id) => fetchPlot(id).then((r) => r.plot)))
      .then(setPlots)
      .catch(() => setPlots([]));
  }, [ids]);

  if (ids.length === 0) return <p className="text-ink/60">{m.empty}</p>;

  const rows: { label: string; value: (p: Plot) => string }[] = [
    { label: m.cadastral, value: (p) => p.cadastral_no },
    { label: "₸", value: (p) => money(p.price_kzt, locale) },
    { label: m.area, value: (p) => `${p.area_sotka} ${m.sotka}` },
    { label: m.purpose, value: (p) => PURPOSE[p.purpose][locale] },
    { label: m.district, value: (p) => p.district },
    { label: m.trust, value: (p) => String(p.trust_score) },
    { label: m.verified, value: (p) => (p.verified ? m.verified : m.unverified) },
    { label: m.gas, value: (p) => UTILITY[p.gas][locale] },
    { label: m.electricity, value: (p) => UTILITY[p.electricity][locale] },
    { label: m.water, value: (p) => UTILITY[p.water][locale] },
    { label: m.relief, value: (p) => RELIEF[p.relief ?? "flat"][locale] },
    { label: m.encumbrances, value: (p) => p.encumbrances || "—" },
  ];

  return (
    <div className="overflow-x-auto border border-ink/10">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-white/70">
            <th className="p-3 text-left font-normal text-ink/45" />
            {plots.map((p) => (
              <th key={p.id} className="p-3 text-left font-serif text-lg">
                <Link href={`/${locale}/plots/${p.slug}`} className="hover:underline">
                  {titleOf(p, locale)}
                </Link>
                {p.photos?.[0] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.photos[0]} alt="" className="mt-2 h-28 w-full object-cover" />
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-ink/10">
              <td className="p-3 text-ink/45 whitespace-nowrap">{row.label}</td>
              {plots.map((p) => (
                <td key={p.id} className="p-3">
                  {row.value(p)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
