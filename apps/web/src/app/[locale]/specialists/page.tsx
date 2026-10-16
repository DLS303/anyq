import { SpecialistsClient } from "@/components/specialists/SpecialistsClient";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function SpecialistsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = raw as Locale;
  const m = t(locale);
  return (
    <div>
      <h1 className="text-2xl sm:text-4xl font-medium tracking-tight mb-4">{m.navSpecialists}</h1>
      <SpecialistsClient locale={locale} />
    </div>
  );
}
