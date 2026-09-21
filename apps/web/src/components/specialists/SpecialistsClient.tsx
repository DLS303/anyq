"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchSpecialists } from "@/lib/api";
import { CATEGORY, money } from "@/lib/format";
import type { Locale, SpecCategory, Specialist } from "@/lib/types";
import { t } from "@/i18n/messages";

const CATS: SpecCategory[] = ["survey", "legal", "architecture", "smr", "supervision", "equipment"];

export function SpecialistsClient({ locale }: { locale: Locale }) {
  const m = t(locale);
  const [category, setCategory] = useState("");
  const [items, setItems] = useState<Specialist[]>([]);

  useEffect(() => {
    fetchSpecialists({ category: category || undefined }).then(setItems).catch(() => setItems([]));
  }, [category]);

  return (
    <div>
      <p className="text-ink/60 mb-4">{m.specialistsLead}</p>
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          type="button"
          onClick={() => setCategory("")}
          className={`px-3 py-1 text-xs border ${!category ? "bg-pine text-paper border-pine" : "border-ink/15"}`}
        >
          {m.any}
        </button>
        {CATS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setCategory(c)}
            className={`px-3 py-1 text-xs border ${category === c ? "bg-pine text-paper border-pine" : "border-ink/15"}`}
          >
            {CATEGORY[c][locale]}
          </button>
        ))}
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        {items.map((s) => (
          <Link key={s.id} href={`/${locale}/specialists/${s.slug}`} className="glass rounded-frost overflow-hidden hover:border-ice/40">
            {s.cover ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={s.cover} alt="" className="h-36 w-full object-cover" />
            ) : null}
            <div className="p-4">
              <p className="text-[11px] uppercase tracking-wider text-ink/45">{CATEGORY[s.category][locale]}</p>
              <h3 className="font-serif text-2xl mt-1">{locale === "kk" ? s.company_kk : s.company_ru}</h3>
              <p className="text-sm mt-2">
                ★ {s.rating || "—"} · {s.reviews_count} {m.reviews.toLowerCase()}
                {s.license_verified ? ` · ${m.license} ${s.license_cat}` : ""}
              </p>
              {s.prices[0] ? (
                <p className="text-sm text-ink/60 mt-1">
                  {locale === "kk" ? s.prices[0].title_kk : s.prices[0].title_ru} · {money(s.prices[0].price_kzt, locale)}
                </p>
              ) : null}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
