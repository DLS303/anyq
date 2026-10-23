import { MarketStorefront } from "@/components/market/MarketStorefront";
import type { Locale } from "@/lib/types";

export default async function SupplierPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  return <MarketStorefront locale={locale as Locale} companyId={id} />;
}
