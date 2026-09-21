import { CatalogClient } from "@/components/catalog/CatalogClient";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function CatalogPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = raw as Locale;
  const m = t(locale);
  return (
    <div>
      <h1 className="font-serif text-4xl mb-6">{m.navCatalog}</h1>
      <CatalogClient locale={locale} />
    </div>
  );
}
