import { LoginView } from "@/components/login/LoginView";
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
  const initialMode = query.mode === "login" ? "login" : "register";
  return (
    <div>
      <LoginView locale={locale} initialMode={initialMode} />
    </div>
  );
}
