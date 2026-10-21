import { Suspense } from "react";
import { MarketHome } from "@/components/market/MarketHome";
import type { Locale } from "@/lib/types";

export default async function MarketPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return (
    <Suspense fallback={<div className="h-48 animate-pulse rounded-3xl bg-slate-200/80" aria-busy="true" />}>
      <MarketHome locale={locale as Locale} />
    </Suspense>
  );
}
