import { ControlPanel, type ControlSection } from "@/components/control/ControlPanel";
import type { Locale } from "@/lib/types";

const SECTIONS: ControlSection[] = ["legal", "estimates", "crm"];

export default async function ControlPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ section?: string }>;
}) {
  const { locale: raw } = await params;
  const locale = (raw === "kk" ? "kk" : "ru") as Locale;
  const query = await searchParams;
  const section = SECTIONS.includes(query.section as ControlSection) ? (query.section as ControlSection) : "legal";
  return <ControlPanel locale={locale} section={section} />;
}
