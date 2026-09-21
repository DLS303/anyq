import { ProjectHub } from "@/components/site/ProjectHub";
import type { Locale } from "@/lib/types";

export default async function SiteProjectPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <ProjectHub locale={locale as Locale} id={id} />;
}
