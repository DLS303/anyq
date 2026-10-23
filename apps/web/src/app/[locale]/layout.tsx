import { notFound } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";
import { messages, type Msg } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

const LOCALES: Locale[] = ["ru", "kk"];

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) notFound();
  const pack = messages[locale as Locale] as Msg;
  return (
    <AppShell locale={locale as Locale} messages={pack}>
      {children}
    </AppShell>
  );
}
