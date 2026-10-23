import { notFound, redirect } from "next/navigation";
import { REGISTRATION_ENABLED } from "@/lib/registration";

export default async function RegisterPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!REGISTRATION_ENABLED) notFound();
  redirect(`/${locale}/login?mode=register`);
}
