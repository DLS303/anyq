import { redirect } from "next/navigation";

export default async function PlotPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale } = await params;
  redirect(`/${locale === "kk" ? "kk" : "ru"}`);
}
