"use client";

import { LongList } from "@/components/ui/LongList";
import { useMessages } from "@/lib/i18n";
import type { Locale, ProcOfferCell, ProcSheetLine } from "@/lib/types";

type Supplier = { name: string; total_kzt: number; vat_mixed: boolean };

function tenge(value: number, locale: Locale) {
  const formatted = new Intl.NumberFormat(locale === "kk" ? "kk-KZ" : "ru-KZ", {
    maximumFractionDigits: 2,
  }).format(value);
  return `${formatted} ₸`;
}

function statusText(code: ProcSheetLine["status_code"], m: ReturnType<typeof useMessages>) {
  switch (code) {
    case "no_price":
      return m.procNoOffers;
    case "one_offer":
      return m.procOneOffer;
    case "no_compare":
      return m.procNoCompare;
    default:
      return m.procCompared;
  }
}

function vatText(value: boolean | null, m: ReturnType<typeof useMessages>) {
  if (value === true) return m.procVatYes;
  if (value === false) return m.procVatNo;
  return m.procVatUnknown;
}

function OfferFacts({
  offer,
  lineQty,
  locale,
  warn,
}: {
  offer: ProcOfferCell;
  lineQty: number;
  locale: Locale;
  warn?: string;
}) {
  const m = useMessages();
  return (
    <span className="block min-w-0">
      <span className={offer.is_best ? "font-semibold" : ""}>{tenge(offer.price_kzt, locale)}</span>
      <span className="mt-1 block text-xs text-ink/60">
        {vatText(offer.vat_included, m)}
        {offer.is_best ? ` · ${m.procBest}` : ""}
        {offer.is_selected ? ` · ${m.procSelected}` : ""}
      </span>
      {warn ? <span className="mt-1 block break-words text-xs text-rose-700">{warn}</span> : null}
      {offer.short && offer.qty_available != null ? (
        <span className="mt-1 block text-xs text-ink/60">
          {m.procShort.replace("{n}", String(offer.qty_available)).replace("{m}", String(lineQty))}
        </span>
      ) : null}
    </span>
  );
}

export function PriceCompare({
  locale,
  lines,
  suppliers,
  canDecide,
  pending,
  warnOf,
  onSelect,
}: {
  locale: Locale;
  lines: ProcSheetLine[];
  suppliers: Supplier[];
  canDecide: boolean;
  pending: boolean;
  warnOf: (offerId: string) => string | undefined;
  onSelect: (lineId: string, offerId: string) => void;
}) {
  const m = useMessages();
  return (
    <>
      <div className="grid min-w-0 gap-3 overflow-x-hidden md:hidden" data-price-cards>
        <LongList
          items={lines}
          pageSize={20}
          getKey={(line) => line.id}
          render={(line) => (
          <article className="min-w-0 rounded-2xl border border-ink/10 bg-white/70 p-3">
            <h3 className="break-words font-medium">
              {line.pos_no}. {line.title}
            </h3>
            <p className="text-xs text-ink/60">
              {line.qty} {line.unit}
              {line.status_code ? ` · ${statusText(line.status_code, m)}` : ""}
            </p>
            <ul className="mt-2 grid gap-2">
              {suppliers.map((item) => {
                const offer = line.cells[item.name] || null;
                const warn = offer ? warnOf(offer.id) : undefined;
                const marked = offer?.is_best ? "border-emerald-600 bg-emerald-100" : "border-ink/10 bg-white";
                if (!offer || !canDecide) {
                  return (
                    <li key={item.name} className={`min-w-0 rounded-xl border px-3 py-2 ${marked}`}>
                      <p className="break-words text-sm font-medium">{item.name}</p>
                      {offer ? (
                        <OfferFacts offer={offer} lineQty={line.qty} locale={locale} warn={warn} />
                      ) : (
                        <p className="text-sm text-ink/40">—</p>
                      )}
                    </li>
                  );
                }
                return (
                  <li key={item.name}>
                    <button
                      type="button"
                      disabled={pending}
                      aria-pressed={offer.is_selected}
                      data-best={offer.is_best ? "true" : "false"}
                      className={`grid min-h-12 w-full min-w-0 grid-cols-[1fr_auto] items-center gap-2 rounded-xl border px-3 py-2 text-left ${marked}`}
                      onClick={() => onSelect(line.id, offer.id)}
                    >
                      <span className="min-w-0">
                        <span className="block break-words text-sm font-medium">{item.name}</span>
                        <OfferFacts offer={offer} lineQty={line.qty} locale={locale} warn={warn} />
                      </span>
                      <span className="text-xs text-pine">{offer.is_selected ? m.procSelected : m.procSelect}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </article>
          )}
        />
        <article className="min-w-0 rounded-2xl border border-ink/10 p-3 text-sm">
          <h3 className="font-medium">{m.procTotal}</h3>
          <ul className="mt-2 grid gap-1">
            {suppliers.map((item) => (
              <li key={item.name} className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 break-words">{item.name}</span>
                <span className="shrink-0 font-medium">
                  {tenge(item.total_kzt, locale)}
                  {item.vat_mixed ? <span className="mt-1 block text-xs font-normal text-ink/60">{m.procVatMixed}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </article>
      </div>
      <div className="hidden max-w-full overflow-x-auto rounded-2xl border border-ink/10 md:block" data-price-table>
        <table className="w-max min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-20 min-w-[8rem] max-w-[10rem] bg-paper px-3 py-3 text-left">{m.procLine}</th>
              {suppliers.map((item) => (
                <th key={item.name} className="min-w-36 bg-paper px-3 py-3 text-left font-medium">
                  {item.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.id}>
                <th className="sticky left-0 z-10 min-w-[8rem] max-w-[10rem] bg-paper px-3 py-3 text-left align-top font-normal">
                  <span className="block break-words font-medium">{line.title}</span>
                  <span className="text-xs text-ink/60">
                    {line.qty} {line.unit} · {statusText(line.status_code, m)}
                  </span>
                </th>
                {suppliers.map((item) => {
                  const offer = line.cells[item.name] || null;
                  const warn = offer ? warnOf(offer.id) : undefined;
                  return (
                    <td
                      key={item.name}
                      className={`px-3 py-3 align-top ${offer?.is_best ? "bg-emerald-100" : ""} ${warn ? "ring-1 ring-inset ring-rose-600" : ""}`}
                    >
                      {offer ? <OfferFacts offer={offer} lineQty={line.qty} locale={locale} warn={warn} /> : <span className="text-ink/40">—</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <th className="sticky left-0 z-10 bg-paper px-3 py-3 text-left">{m.procTotal}</th>
              {suppliers.map((item) => (
                <td key={item.name} className="px-3 py-3 font-medium">
                  {tenge(item.total_kzt, locale)}
                  {item.vat_mixed ? <span className="mt-1 block text-xs font-normal text-ink/60">{m.procVatMixed}</span> : null}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
