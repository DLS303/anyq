"use client";

import Link from "next/link";
import { displayPriceTiyn, formatTiyn, medianText, type MarketCardItem } from "@/lib/market";

export function MarketCard({
  locale,
  item,
  inBasket,
  onAdd,
}: {
  locale: string;
  item: MarketCardItem;
  inBasket: boolean;
  onAdd: () => void;
}) {
  const price = formatTiyn(displayPriceTiyn(item.price_tiyn, item.vat_included, item.vat_rate));
  const score = item.label || `${item.rating.toFixed(1).replace(".", ",")} · ${item.deal_count}`;

  return (
    <article className="rounded-3xl border border-slate-200/90 bg-white p-4 shadow-luxury">
      <div className="flex items-start justify-between gap-3">
        <h2 className="min-w-0 break-words text-base font-semibold leading-snug text-ink">{item.name}</h2>
        {item.badge ? (
          <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800">
            {item.badge}
          </span>
        ) : null}
      </div>
      <p className="mt-3 text-3xl font-bold tracking-tight text-pine">{price}</p>
      <p className="mt-1 text-sm text-slate-600">
        за {item.unit}
        <span className="mx-1.5 text-slate-300">·</span>
        <span>{item.vat_label}</span>
      </p>
      {item.stale_label ? <p className="mt-1 text-sm font-medium text-amber-800">{item.stale_label}</p> : null}
      <p className="mt-1 text-sm text-slate-500">{medianText(item.median_label, item.median_tiyn)}</p>
      <Link href={`/${locale}/market/supplier/${item.supplier_id}`} className="mt-3 block text-sm font-medium text-ink">
        {item.supplier_name}
      </Link>
      <p className="text-sm text-slate-600">
        {item.city}
        <span className="mx-1.5 text-slate-300">·</span>
        <span>{item.availability}</span>
      </p>
      <p className="mt-1 text-sm text-slate-500">{score}</p>
      <button
        type="button"
        className="mt-4 inline-flex min-h-14 w-full items-center justify-center rounded-full bg-pine px-4 text-base font-semibold text-white shadow-luxury disabled:bg-slate-200 disabled:text-slate-500"
        onClick={onAdd}
        disabled={inBasket}
      >
        {inBasket ? "В заявке" : "В заявку"}
      </button>
    </article>
  );
}
