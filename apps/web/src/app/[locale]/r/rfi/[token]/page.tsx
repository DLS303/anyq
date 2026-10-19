import type { Metadata } from "next";
import { RfiReply } from "@/components/site/RfiReply";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; token: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const m = t(locale === "kk" ? "kk" : "ru");
  return {
    title: m.rfiReplyTitle,
    robots: { index: false, follow: false },
    referrer: "no-referrer",
  };
}

export default async function PublicRfiPage({
  params,
}: {
  params: Promise<{ locale: string; token: string }>;
}) {
  const { locale: rawLocale, token } = await params;
  const locale: Locale = rawLocale === "kk" ? "kk" : "ru";
  return <RfiReply locale={locale} token={token} />;
}
