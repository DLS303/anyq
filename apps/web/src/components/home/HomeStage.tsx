import Link from "next/link";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export function HomeStage({ locale }: { locale: Locale }) {
  const m = t(locale);
  return (
    <section className="mx-auto grid max-w-3xl gap-4 py-12 sm:gap-5 sm:py-20">
      <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-5xl">{m.heroTitle}</h1>
      <p className="max-w-xl text-base leading-7 text-slate-600">{m.heroLead}</p>
      <Link
        href={`/${locale}/login?mode=register`}
        data-register-cta
        className="btn-ice inline-flex min-h-12 w-fit items-center px-5 text-sm font-semibold"
      >
        {m.heroRegister}
      </Link>
    </section>
  );
}
