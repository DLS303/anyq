"use client";

import Link from "next/link";
import { Briefcase, Calculator, Scale, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Locale } from "@/lib/types";
import { CrmBoard } from "@/components/crm/CrmBoard";
import { EstimateClient } from "@/components/estimates/EstimateClient";
import { AiPanel } from "./AiPanel";
import { LegalPanel } from "./LegalPanel";

export const CONTROL_SECTIONS = ["legal", "estimates", "ai", "crm"] as const;
export type ControlSection = (typeof CONTROL_SECTIONS)[number];

const ITEMS: { id: ControlSection; label: string; icon: LucideIcon }[] = [
  { id: "legal", label: "Юридические вопросы", icon: Scale },
  { id: "estimates", label: "Сметы", icon: Calculator },
  { id: "ai", label: "ИИ", icon: Sparkles },
  { id: "crm", label: "CRM", icon: Briefcase },
];

export function ControlPanel({ locale, section }: { locale: Locale; section: ControlSection }) {
  return (
    <div>
      <div className="mb-4 lg:hidden">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-950">Панель управления</h1>
        <div className="tab-scroll mt-3">
          {ITEMS.map((item) => (
            <SectionLink key={item.id} locale={locale} item={item} active={section === item.id} />
          ))}
        </div>
      </div>

      <div className="lg:grid lg:grid-cols-[13.75rem_minmax(0,1fr)] lg:items-start lg:gap-10">
        <aside className="sticky top-24 hidden lg:block">
          <h1 className="text-[15px] font-semibold tracking-tight text-slate-950">Панель управления</h1>
          <p className="mt-1 text-xs leading-5 text-slate-500">Юридические вопросы, сметы, ИИ и CRM.</p>
          <nav className="mt-4 grid gap-0.5" aria-label="Разделы панели">
            {ITEMS.map((item) => (
              <SectionLink key={item.id} locale={locale} item={item} active={section === item.id} />
            ))}
          </nav>
        </aside>

        <div className="min-w-0">
          {section === "legal" ? <LegalPanel locale={locale} /> : null}
          {section === "estimates" ? <EstimateClient locale={locale} embedded /> : null}
          {section === "ai" ? <AiPanel /> : null}
          {section === "crm" ? (
            <div className="space-y-4">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">CRM</h2>
                <p className="mt-1 text-sm text-slate-500">Сделки, лиды, счета и шахматка.</p>
              </div>
              <CrmBoard locale={locale} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function SectionLink({
  locale,
  item,
  active,
}: {
  locale: Locale;
  item: (typeof ITEMS)[number];
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={`/${locale}/control?section=${item.id}`}
      aria-current={active ? "page" : undefined}
      className={`flex min-h-11 items-center gap-2.5 rounded-xl px-3 py-2 text-sm ${
        active ? "bg-white font-medium text-slate-950 shadow-sm" : "text-slate-600 hover:bg-white/70"
      }`}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}
