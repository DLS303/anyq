import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function ModerationPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = (raw === "kk" ? "kk" : "ru") as Locale;
  const m = t(locale);
  return (
    <div className="mx-auto grid max-w-2xl gap-3">
      <h1 className="font-serif text-4xl">{m.queueTitle}</h1>
      <p className="text-sm leading-relaxed text-ink/70">{m.moderationClosed}</p>
    </div>
  );
}
