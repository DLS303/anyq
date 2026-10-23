import { SignUpWindow } from "@/components/signup/SignUpWindow";
import type { Locale } from "@/lib/types";

export default async function RegisterPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const safe: Locale = locale === "kk" ? "kk" : "ru";
  return <SignUpWindow locale={safe} />;
}
