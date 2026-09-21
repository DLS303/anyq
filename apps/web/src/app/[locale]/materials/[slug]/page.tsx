import { notFound } from "next/navigation";
import { MaterialView } from "@/components/materials/MaterialView";
import { fetchMaterial } from "@/lib/api";
import type { Locale } from "@/lib/types";

export default async function MaterialPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  const item = await fetchMaterial(slug).catch(() => null);
  if (!item) notFound();
  return <MaterialView locale={locale as Locale} item={item} />;
}
