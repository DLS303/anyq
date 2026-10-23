import { LoginView } from "@/components/login/LoginView";
import { registerLink } from "@/lib/registration";
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
  const initialMode = registerLink(locale) && query.mode !== "login" ? "register" : "login";
  return (
    <div>
      <LoginView locale={locale} initialMode={initialMode} />
    </div>
  );
}
