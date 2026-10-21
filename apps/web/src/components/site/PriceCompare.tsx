"use client";

import { t } from "@/i18n/messages";
import type { Locale, ProcOfferCell, ProcSheetLine } from "@/lib/types";

type Supplier = { name: string; total_kzt: number; vat_mixed: boolean };

function tenge(value: number, locale: Locale) {
  const formatted = new Intl.NumberFormat(locale === "kk" ? "kk-KZ" : "ru-KZ", {
    maximumFractionDigits: 2,
  }).format(value);
  return `${formatted} ₸`;
}

function statusText(code: ProcSheetLine["status_code"], m: ReturnType<typeof t>) {
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

function vatText(value: boolean | null, m: ReturnType<typeof t>) {
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
  const m = t(locale);
  return (
    <span className="block min-w-0">
      <span className={offer.is_best ? "font-semibold" : ""}>{tenge(offer.price_kzt, locale)}</span>
      <span className="mt-1 block text-xs text-ink/60">
        {vatText(offer.vat_included, m)}
        {offer.is_best ? ` · ${m.procBest}` : ""}
        {offer.is_selected ? ` · ${m.procSelected}` : ""}
      </span>
      {offer.suspicious && !offer.suspicion_confirmed ? (
        <span className="mt-1 block text-xs text-amber-800">{m.procSuspicious}</span>
      ) : null}
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
  onConfirm,
}: {
  locale: Locale;
  lines: ProcSheetLine[];
  suppliers: Supplier[];
  canDecide: boolean;
  pending: boolean;
  warnOf: (offerId: string) => string | undefined;
  onSelect: (lineId: string, offerId: string) => void;
  onConfirm?: (offerId: string) => void;
}) {
  const m = t(locale);
  return (
    <>
      <div className="grid min-w-0 gap-3 overflow-x-hidden md:hidden" data-price-cards>
        {lines.map((line) => {
          const priced = suppliers.filter((item) => line.cells[item.name]);
          const columns = Math.min(3, Math.max(priced.length, 1));
          return (
          <article key={line.id} className="min-w-0 rounded-2xl border border-ink/10 bg-white/70 p-3">
            <h3 className="break-words font-medium">
              {line.pos_no}. {line.title}
            </h3>
            <p className="text-xs text-ink/60">
              {line.qty} {line.unit}
              {line.status_code ? ` · ${statusText(line.status_code, m)}` : ""}
            </p>
            <div
              className="mt-2 grid gap-1.5"
              data-supplier-grid
              style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
            >
              {priced.map((item) => {
                const offer = line.cells[item.name];
                if (!offer) return null;
                const warn = warnOf(offer.id);
                const held = Boolean(offer.suspicious && !offer.suspicion_confirmed);
                const marked = offer.is_best ? "border-emerald-600 bg-emerald-100" : "border-ink/10 bg-white";
                if (held && onConfirm) {
                  return (
                    <button
                      key={item.name}
                      type="button"
                      data-suspicious="true"
                      className={`min-h-12 min-w-0 rounded-xl border px-1.5 py-2 text-left ${marked}`}
                      onClick={() => onConfirm(offer.id)}
                    >
                      <span className="block break-words text-[11px] font-medium leading-tight">{item.name}</span>
                      <OfferFacts offer={offer} lineQty={line.qty} locale={locale} warn={warn} />
                      <span className="mt-1 block text-[11px] text-pine">{m.procConfirmPrice}</span>
                    </button>
                  );
                }
                if (!canDecide) {
                  return (
                    <div key={item.name} className={`min-w-0 rounded-xl border px-1.5 py-2 ${marked}`}>
                      <p className="break-words text-[11px] font-medium leading-tight">{item.name}</p>
                      <OfferFacts offer={offer} lineQty={line.qty} locale={locale} warn={warn} />
                    </div>
                  );
                }
                return (
                  <button
                    key={item.name}
                    type="button"
                    disabled={pending}
                    aria-pressed={offer.is_selected}
                    data-best={offer.is_best ? "true" : "false"}
                    data-offer={offer.id}
                    className={`min-h-12 min-w-0 rounded-xl border px-1.5 py-2 text-left ${marked}`}
                    onClick={() => onSelect(line.id, offer.id)}
                  >
                    <span className="block break-words text-[11px] font-medium leading-tight">{item.name}</span>
                    <OfferFacts offer={offer} lineQty={line.qty} locale={locale} warn={warn} />
                    <span className="mt-1 block text-[11px] text-pine">{offer.is_selected ? m.procSelected : m.procSelect}</span>
                  </button>
                );
              })}
            </div>
          </article>
          );
        })}
        <article className="min-w-0 rounded-2xl border border-ink/10 p-3 text-sm">
          <h3 className="font-medium">{m.procTotal}</h3>
          <ul
            className="mt-2 grid gap-1.5"
            data-supplier-totals
            style={{ gridTemplateColumns: `repeat(${Math.min(3, Math.max(suppliers.length, 1))}, minmax(0, 1fr))` }}
          >
            {suppliers.map((item) => (
              <li key={item.name} className="min-w-0">
                <span className="block break-words text-[11px] leading-tight">{item.name}</span>
                <span className="font-medium">
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
