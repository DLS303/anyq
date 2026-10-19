import { redirect } from "next/navigation";
import { PilotCrm } from "@/components/crm/PilotCrm";
import { PILOT_MODE } from "@/lib/pilot";
import type { Locale } from "@/lib/types";

export default async function CrmPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = (raw === "kk" ? "kk" : "ru") as Locale;
  if (PILOT_MODE) return <PilotCrm locale={locale} />;
  redirect(`/${locale}/control?section=crm`);
}
