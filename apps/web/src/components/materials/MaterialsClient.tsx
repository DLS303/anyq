"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchMaterials } from "@/lib/api";
import { MATERIAL_CAT, money } from "@/lib/format";
import type { Locale, Material, MaterialCat } from "@/lib/types";
import { t } from "@/i18n/messages";

const CATS: MaterialCat[] = ["inert", "brick", "mix", "metal", "roofing", "lumber", "concrete"];

export function MaterialsClient({ locale }: { locale: Locale }) {
  const m = t(locale);
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Material[]>([]);

  useEffect(() => {
    fetchMaterials({ category: category || undefined, q: q || undefined })
      .then(setItems)
      .catch(() => setItems([]));
  }, [category, q]);

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-4">
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
            {MATERIAL_CAT[c][locale]}
          </button>
        ))}
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={m.search}
        className="border border-ink/15 px-3 py-2 text-sm mb-6 w-full max-w-md"
      />
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map((item) => (
          <Link key={item.id} href={`/${locale}/materials/${item.slug}`} className="glass rounded-frost overflow-hidden hover:border-ice/40">
            {item.photo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.photo} alt="" className="h-36 w-full object-cover" />
            ) : (
              <div className="h-36 bg-mist" />
            )}
            <div className="p-4">
              <p className="text-[11px] uppercase tracking-wider text-ink/45">{MATERIAL_CAT[item.category][locale]}</p>
              <h3 className="font-serif text-xl mt-1">{locale === "kk" ? item.title_kk : item.title_ru}</h3>
              <p className="mt-2 font-medium">
                {money(item.price_kzt, locale)} / {item.unit}
              </p>
              <p className="text-xs text-ink/50 mt-1">
                {item.city} · min {item.min_qty} {item.unit}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
