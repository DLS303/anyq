import { ChatApp } from "@/components/chat/ChatApp";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function ChatPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = raw as Locale;
  const m = t(locale);
  return (
    <div>
      <h1 className="font-serif text-4xl mb-4">{m.navChat}</h1>
      <ChatApp locale={locale} />
    </div>
  );
}
