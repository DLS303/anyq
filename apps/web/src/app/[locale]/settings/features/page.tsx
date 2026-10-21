import { ObjectFeatures } from "@/components/settings/ObjectFeatures";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function ObjectFeaturesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = raw as Locale;
  const m = t(locale);
  return (
    <div className="max-w-xl">
      <p className="text-sm text-ink/60">
        {m.settings}
        {" · "}
        {m.objectFeatures}
      </p>
      <h1 className="mb-4 font-serif text-3xl">{m.objectFeatures}</h1>
      <ObjectFeatures locale={locale} />
    </div>
  );
}
