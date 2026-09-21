import { PublishForm } from "@/components/publish/PublishForm";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function PublishPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ id?: string }>;
}) {
  const { locale: raw } = await params;
  const { id } = await searchParams;
  const locale = raw as Locale;
  const m = t(locale);
  return (
    <div>
      <h1 className="font-serif text-4xl mb-4">{id ? m.edit : m.publishTitle}</h1>
      <PublishForm locale={locale} editId={id} />
    </div>
  );
}
