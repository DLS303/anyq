import { redirect } from "next/navigation";

export default async function CrmPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = raw === "kk" ? "kk" : "ru";
  redirect(`/${locale}/control?section=crm`);
}
