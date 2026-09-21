import { notFound } from "next/navigation";
import { SpecialistProfile } from "@/components/specialists/SpecialistProfile";
import { fetchSpecialist } from "@/lib/api";
import type { Locale } from "@/lib/types";

export default async function SpecialistPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  const result = await fetchSpecialist(slug).catch(() => null);
  if (!result) notFound();
  return <SpecialistProfile locale={locale as Locale} specialist={result.specialist} reviews={result.reviews} />;
}
