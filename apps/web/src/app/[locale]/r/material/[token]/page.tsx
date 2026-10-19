import type { Metadata } from "next";
import { MaterialReply } from "@/components/site/MaterialReply";
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
    title: m.matReplyTitle,
    robots: { index: false, follow: false },
    referrer: "no-referrer",
  };
}

export default async function PublicMaterialPage({
  params,
}: {
  params: Promise<{ locale: string; token: string }>;
}) {
  const { locale: rawLocale, token } = await params;
  const locale: Locale = rawLocale === "kk" ? "kk" : "ru";
  return <MaterialReply locale={locale} token={token} />;
}
