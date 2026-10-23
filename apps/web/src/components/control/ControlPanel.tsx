"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { Briefcase, Calculator, Scale } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Locale } from "@/lib/types";
import { ChunkFallback } from "@/components/ui/ChunkFallback";
import { WidgetBoundary } from "@/components/ui/WidgetBoundary";
import { useMessages } from "@/lib/i18n";
import { loadWithin } from "@/lib/loadWithin";
import { LegalPanel } from "./LegalPanel";

const EstimateClient = dynamic(
  () => loadWithin(import("@/components/estimates/EstimateClient").then((m) => m.EstimateClient)),
  { loading: () => <ChunkFallback /> },
);

const CrmBoard = dynamic(
  () => loadWithin(import("@/components/crm/CrmBoard").then((m) => m.CrmBoard)),
  { loading: () => <ChunkFallback /> },
);

export const CONTROL_SECTIONS = ["legal", "estimates", "crm"] as const;
export type ControlSection = (typeof CONTROL_SECTIONS)[number];

const ITEMS: { id: ControlSection; label: string; icon: LucideIcon }[] = [
  { id: "legal", label: "Юридические вопросы", icon: Scale },
  { id: "estimates", label: "Сметы", icon: Calculator },
  { id: "crm", label: "CRM", icon: Briefcase },
];

export function ControlPanel({ locale, section }: { locale: Locale; section: ControlSection }) {
  const m = useMessages();
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
          <p className="mt-1 text-xs leading-5 text-slate-500">Юридические вопросы, сметы и CRM.</p>
          <nav className="mt-4 grid gap-0.5" aria-label="Разделы панели">
            {ITEMS.map((item) => (
              <SectionLink key={item.id} locale={locale} item={item} active={section === item.id} />
            ))}
          </nav>
        </aside>

        <div className="min-w-0">
          {section === "legal" ? <LegalPanel locale={locale} /> : null}
          {section === "estimates" ? (
            <WidgetBoundary message={m.widgetError} retryLabel={m.retry}>
              <EstimateClient locale={locale} embedded />
            </WidgetBoundary>
          ) : null}
          {section === "crm" ? (
            <div className="space-y-4">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">CRM</h2>
                <p className="mt-1 text-sm text-slate-500">Сделки, лиды, счета и шахматка.</p>
              </div>
              <WidgetBoundary message={m.widgetError} retryLabel={m.retry}>
                <CrmBoard locale={locale} />
              </WidgetBoundary>
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
