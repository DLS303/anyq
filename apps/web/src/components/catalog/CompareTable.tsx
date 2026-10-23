"use client";

import Link from "next/link";
import { fetchPlot } from "@/lib/api";
import { PURPOSE, RELIEF, UTILITY, money, titleOf } from "@/lib/format";
import { ErrorRetry, LoadingSkeleton, useAsync } from "@/lib/useAsync";
import type { Locale, Plot } from "@/lib/types";
import { useMessages } from "@/lib/i18n";
import { AuthImage } from "@/components/media/AuthImage";

export function CompareTable({ locale, ids }: { locale: Locale; ids: string[] }) {
  const m = useMessages();
  const query = useAsync(
    (signal) => Promise.all(ids.map((id) => fetchPlot(id, undefined, signal).then((row) => row.plot))),
    [ids.join(",")],
  );
  const plots = query.data ?? [];

  if (ids.length === 0) return <p className="text-ink/60">{m.empty}</p>;
  if (query.loading) return <LoadingSkeleton label={m.hubLoading} />;
  if (query.status === "error") {
    return <ErrorRetry message={m.listLoadError} retryLabel={m.retry} onRetry={query.reload} />;
  }
  if (plots.length === 0) return <p className="text-ink/60">{m.empty}</p>;

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
                  <AuthImage src={p.photos[0]} alt="" className="mt-2 h-28 w-full object-cover" />
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
