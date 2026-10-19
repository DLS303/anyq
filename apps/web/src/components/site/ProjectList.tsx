"use client";

import Link from "next/link";
import { fetchProjects } from "@/lib/api";
import { money } from "@/lib/format";
import { t } from "@/i18n/messages";
import { ErrorRetry, LoadingSkeleton, useAsync } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

type Snap = {
  project: { id: string; slug: string; title: string; address: string };
  health: string;
  budget_kzt: number;
  open_rfi: number;
  open_punch: number;
};

function healthLabel(health: string, locale: Locale) {
  const m = t(locale);
  if (health === "green") return m.healthOk;
  if (health === "red") return m.healthBad;
  return m.healthWarn;
}

export function ProjectList({ locale }: { locale: Locale }) {
  const m = t(locale);
  const query = useAsync(() => fetchProjects() as Promise<Snap[]>, []);
  const items = query.data ?? [];

  if (query.loading) return <LoadingSkeleton label={m.hubLoading} />;
  if (query.status === "error") {
    return <ErrorRetry message={m.listLoadError} retryLabel={m.hubRetry} onRetry={query.reload} />;
  }
  if (!items.length) {
    return (
      <div className="border border-ink/10 bg-white/50 p-6 text-center">
        <p className="text-sm text-ink/70">{m.listEmpty}</p>
        <Link href={`/${locale}/crm`} className="mt-4 inline-flex min-h-12 items-center text-sm underline">
          {m.hubFromCrm}
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {items.map((row) => (
        <Link
          key={row.project.id}
          href={`/${locale}/site/${row.project.id}`}
          className="border border-ink/10 bg-white/60 p-5 hover:border-pine"
        >
          <div className="flex justify-between gap-4">
            <div className="min-w-0">
              <h2 className="font-serif text-2xl">{row.project.title}</h2>
              <p className="mt-1 text-sm text-ink/55">{row.project.address}</p>
            </div>
            <p className="text-xs uppercase tracking-wider">{healthLabel(row.health, locale)}</p>
          </div>
          <p className="mt-3 text-sm">
            {money(row.budget_kzt, locale)} · {m.hubIssueRfi} {row.open_rfi} · {m.hubIssuePunch} {row.open_punch}
          </p>
        </Link>
      ))}
    </div>
  );
}
