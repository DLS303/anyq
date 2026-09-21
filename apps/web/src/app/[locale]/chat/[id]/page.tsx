import { ChatApp } from "@/components/chat/ChatApp";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function ChatThreadPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  const m = t(locale as Locale);
  return (
    <div>
      <h1 className="font-serif text-4xl mb-4">{m.navChat}</h1>
      <ChatApp locale={locale as Locale} threadId={id} />
    </div>
  );
}
