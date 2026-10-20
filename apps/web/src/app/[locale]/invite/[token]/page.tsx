import { InviteAccept } from "@/components/invites/InviteAccept";
import type { Locale } from "@/lib/types";

export default async function InvitePage({ params }: { params: Promise<{ locale: string; token: string }> }) {
  const { locale: raw, token } = await params;
  const locale = raw as Locale;
  return <InviteAccept locale={locale} token={token} />;
}
