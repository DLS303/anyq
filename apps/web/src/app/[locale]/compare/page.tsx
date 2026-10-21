import { redirect } from "next/navigation";

export default async function ComparePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  redirect(`/${locale === "kk" ? "kk" : "ru"}`);
}
