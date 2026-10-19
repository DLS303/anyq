"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchProjects } from "@/lib/api";
import { money } from "@/lib/format";
import { t } from "@/i18n/messages";
import { PILOT_MODE } from "@/lib/pilot";
import type { Locale } from "@/lib/types";
import { useParams } from "next/navigation";

type Snap = {
  project: { id: string; slug: string; title: string; address: string };
  health: string;
  budget_kzt: number;
  open_rfi: number;
  open_punch: number;
};

export default function SiteListPage() {
  const params = useParams<{ locale: string }>();
  const locale = (params.locale as Locale) || "ru";
  const m = t(locale);
  const [items, setItems] = useState<Snap[]>([]);

  useEffect(() => {
    fetchProjects()
      .then((rows) => setItems(rows as unknown as Snap[]))
      .catch(() => setItems([]));
  }, []);

  return (
    <div>
      <h1 className="text-2xl sm:text-4xl font-medium tracking-tight mt-2 mb-2">{PILOT_MODE ? m.navObjects : m.navSite}</h1>
      <p className="text-ink/60 mb-6 max-w-2xl">
        {PILOT_MODE
          ? m.siteLead
          : "Журнал, RFI, согласования, дефекты, инспекции, ТБ, актуальный комплект чертежей, график, бюджет и табель — один проект, одна правда."}
      </p>
      <div className="grid gap-3">
        {items.map((s) => (
          <Link key={s.project.id} href={`/${locale}/site/${s.project.id}`} className="border border-ink/10 bg-white/60 p-5 hover:border-pine">
            <div className="flex justify-between gap-4">
              <div>
                <h2 className="font-serif text-2xl">{s.project.title}</h2>
                <p className="text-sm text-ink/55 mt-1">{s.project.address}</p>
              </div>
              <p className="text-xs uppercase tracking-wider">
                {PILOT_MODE ? (s.health === "green" ? m.healthOk : s.health === "red" ? m.healthBad : m.healthWarn) : s.health}
              </p>
            </div>
            <p className="text-sm mt-3">
              {money(s.budget_kzt, locale)} · RFI {s.open_rfi} · punch {s.open_punch}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
