import { redirect } from "next/navigation";
import { SignUpWindow } from "@/components/signup/SignUpWindow";
import { REGISTRATION_ENABLED } from "@/lib/registration";
import type { Locale } from "@/lib/types";

export default async function RegisterPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const safe: Locale = locale === "kk" ? "kk" : "ru";
  if (!REGISTRATION_ENABLED) redirect(`/${safe}/login`);
  return <SignUpWindow locale={safe} />;
}
