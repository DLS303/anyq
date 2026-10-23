"use client";

import { useState } from "react";
import { openProcFile } from "@/lib/api";
import { money } from "@/lib/format";
import { toast } from "@/lib/toast";
import { useMessages } from "@/lib/i18n";
import type { Locale, ProcSavings } from "@/lib/types";

function fill(template: string, values: Record<string, string | number>) {
  return Object.entries(values).reduce((text, [key, value]) => text.split(`{${key}}`).join(String(value)), template);
}

function share(value: number) {
  return Math.round(value * 100);
}

function offerDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  return `${match[3]}.${match[2]}.${match[1]}`;
}

function thousands(total: number, locale: Locale) {
  const formatted = new Intl.NumberFormat(locale === "kk" ? "kk-KZ" : "ru-KZ").format(Math.round(total / 1000));
  return `${formatted} тыс. ₸`;
}

export function SavingsBanner({ locale, savings }: { locale: Locale; savings: ProcSavings }) {
  const m = useMessages();
  const [open, setOpen] = useState(false);
  const pct = share(savings.savings_pct);
  const overTotal = savings.overprice.reduce((sum, item) => sum + (item.total_kzt || item.total || 0), 0);
  const overText =
    savings.overprice.length === 1
      ? fill(m.savingsOverOne, { sum: thousands(overTotal, locale) })
      : fill(m.savingsOverMany, { n: savings.overprice.length, sum: thousands(overTotal, locale) });
  const disclaimer = savings.last_offer_date
    ? fill(m.savingsDisclaimer, { date: offerDate(savings.last_offer_date) })
    : m.savingsDisclaimerNoDate;

  return (
    <section className="grid gap-2 rounded-2xl border border-ink/10 bg-white/80 p-4" data-savings-banner>
      <p className="text-sm text-ink/60">{m.savingsTitle}</p>
      <p className="text-2xl font-medium leading-tight">
        {savings.savings_kzt > 0 ? (
          <>
            {money(savings.savings_kzt, locale)} <span className="text-lg">({pct}%)</span>
          </>
        ) : (
          m.savingsNone
        )}
      </p>
      {savings.overprice.length ? <p className="text-sm font-medium text-rose-700">{overText}</p> : null}
      {savings.duplicates.length ? <p className="text-sm font-medium text-rose-700">{m.savingsDuplicate}</p> : null}
      <button type="button" className="w-fit text-sm underline" onClick={() => setOpen((value) => !value)}>
        {open ? m.savingsHide : m.savingsOpen}
      </button>
      {open ? (
        <div className="grid gap-3">
          {savings.lines.map((line) => (
            <article key={line.line_id} className={`grid gap-1 text-sm ${line.included ? "" : "text-ink/45"}`}>
              <p className="break-words font-medium">{line.title}</p>
              {line.reason ? <p>{line.reason}</p> : null}
              <p>
                {m.savingsChosen}: {line.selected ? money(line.selected.price_kzt, locale) : "—"}
                {line.selected?.source_doc_id ? (
                  <>
                    {" "}
                    <button
                      type="button"
                      className="underline"
                      onClick={() =>
                        void openProcFile(`/v1/procurement/documents/${line.selected?.source_doc_id}/file`).catch((err: unknown) =>
                          toast(err instanceof Error ? err.message : m.hubSaveError),
                        )
                      }
                    >
                      {m.savingsSource}
                    </button>
                  </>
                ) : null}
              </p>
              <p>
                {m.savingsSecond}: {line.second ? money(line.second.price_kzt, locale) : "—"}
              </p>
              {line.included ? (
                <p>
                  {m.savingsAmount}: {money(Math.round(line.saving_kzt), locale)}
                </p>
              ) : null}
            </article>
          ))}
          {savings.overprice.map((item) => (
            <p key={item.offer_id} className="text-sm text-rose-700">
              {item.title}: +{money(item.total_kzt, locale)}
            </p>
          ))}
        </div>
      ) : null}
      <p className="text-xs leading-5 text-ink/50">{disclaimer}</p>
    </section>
  );
}
