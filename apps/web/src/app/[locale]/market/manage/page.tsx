import { MarketManage } from "@/components/market/MarketManage";
import type { Locale } from "@/lib/types";

export default async function ManagePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <MarketManage locale={locale as Locale} />;
}
