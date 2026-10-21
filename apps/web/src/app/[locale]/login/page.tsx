import { LoginView } from "@/components/login/LoginView";
import { REGISTRATION_ENABLED } from "@/lib/features";
import { PILOT_MODE } from "@/lib/pilot";
import type { Locale } from "@/lib/types";

export default async function LoginPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ mode?: string }>;
}) {
  const { locale: raw } = await params;
  const query = await searchParams;
  const locale = raw as Locale;
  const initialMode =
    (PILOT_MODE && !(REGISTRATION_ENABLED && query.mode === "register")) || query.mode === "login"
      ? "login"
      : "register";
  return (
    <div>
      <LoginView locale={locale} initialMode={initialMode} />
    </div>
  );
}
