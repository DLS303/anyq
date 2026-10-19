"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { DEMO_MODE } from "@/lib/features";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

const SiteStage = dynamic(() => import("./SiteStage").then((m) => m.SiteStage), {
  ssr: false,
  loading: () => (
    <div
      className="relative ml-[calc(50%-50vw)] mr-[calc(50%-50vw)] h-[250vh] w-screen bg-[#101726]"
      aria-hidden
    />
  ),
});

export function HomeStage({ locale }: { locale: Locale }) {
  if (!DEMO_MODE) {
    const m = t(locale);
    return (
      <section className="mx-auto grid max-w-3xl gap-6 py-10 sm:py-16">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-pine">{m.brand}</p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-5xl">{m.heroTitle}</h1>
        <p className="max-w-xl text-base leading-7 text-slate-600">{m.heroLead}</p>
        <div className="flex flex-wrap gap-3">
          <Link href={`/${locale}/login`} className="btn-ice inline-flex min-h-12 items-center px-5 text-sm font-semibold">
            {m.navLogin}
          </Link>
          <Link href={`/${locale}/site`} className="inline-flex min-h-12 items-center rounded-full border border-ink/15 px-5 text-sm">
            {m.navObjects}
          </Link>
        </div>
      </section>
    );
  }
  return <SiteStage locale={locale} />;
}
