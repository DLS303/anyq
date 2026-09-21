import { notFound } from "next/navigation";
import { PassportView } from "@/components/passport/PassportView";
import { fetchPlot } from "@/lib/api";
import type { Locale } from "@/lib/types";

export default async function PlotPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  const result = await fetchPlot(id).catch(() => null);
  if (!result) notFound();
  return (
    <PassportView
      plot={result.plot}
      calc={result.calc}
      favorite={result.favorite}
      locale={locale as Locale}
    />
  );
}
