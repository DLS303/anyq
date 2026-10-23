import { LoginView } from "@/components/login/LoginView";
import { PILOT_MODE } from "@/lib/pilot";
import { loginInitialMode } from "@/lib/registration";
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
  const initialMode = loginInitialMode(query.mode, PILOT_MODE);
  return (
    <div>
      <LoginView locale={locale} initialMode={initialMode} />
    </div>
  );
}
