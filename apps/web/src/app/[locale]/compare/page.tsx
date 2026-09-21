import { CompareTable } from "@/components/catalog/CompareTable";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function ComparePage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ ids?: string }>;
}) {
  const { locale: raw } = await params;
  const { ids } = await searchParams;
  const locale = raw as Locale;
  const m = t(locale);
  const list = (ids ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 3);
  return (
    <div>
      <h1 className="font-serif text-4xl mb-6">{m.compareOpen}</h1>
      <CompareTable locale={locale} ids={list} />
    </div>
  );
}
