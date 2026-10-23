import { MarketCompare } from "@/components/market/MarketCompare";
import type { Locale } from "@/lib/types";

export default async function RequestPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  return <MarketCompare locale={locale as Locale} requestId={id} />;
}
