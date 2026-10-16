import { EstimateClient } from "@/components/estimates/EstimateClient";
import type { Locale } from "@/lib/types";

export default async function EstimatesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = (raw === "kk" ? "kk" : "ru") as Locale;
  return <EstimateClient locale={locale} />;
}
