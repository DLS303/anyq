"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";
import { CompareProvider, useCompare } from "@/lib/compare";
import type { Locale } from "@/lib/types";
import { t } from "@/i18n/messages";

function otherLocale(locale: Locale): Locale {
  return locale === "ru" ? "kk" : "ru";
}

function swapLocale(pathname: string, locale: Locale) {
  const next = otherLocale(locale);
  return pathname.replace(/^\/(ru|kk)/, `/${next}`) || `/${next}`;
}

function Header({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const link = (path: string) => `/${locale}${path}`;
  const nav: { href: string; label: string }[] = [
    { href: link("/catalog"), label: m.navCatalog },
    { href: link("/materials"), label: m.navMaterials },
    { href: link("/specialists"), label: m.navSpecialists },
    { href: link("/site"), label: m.navSite },
    { href: link("/crm"), label: m.navCrm },
    { href: link("/chat"), label: m.navChat },
    { href: link("/publish"), label: m.navPublish },
    { href: link("/cabinet"), label: m.navCabinet },
  ];
  if (user?.role === "moderator" || user?.role === "admin") {
    nav.push({ href: link("/moderation"), label: m.navModeration });
  }

  const word = locale === "kk" ? "АНЫҚ" : "ANYQ";
  const sub = locale === "kk" ? "ANYQ" : "АНЫҚ";

  return (
    <header className="sticky top-3 z-30 px-3">
      <div className="glass mx-auto flex max-w-6xl items-center gap-4 rounded-full px-4 py-2.5">
        <Link href={link("")} className="flex items-center gap-2.5 shrink-0">
          <span className="grid h-9 w-9 place-items-center rounded-full border border-pine text-[11px] font-semibold tracking-[0.12em] text-pine">
            AQ
          </span>
          <span className="leading-tight">
            <span className="block text-[17px] font-semibold tracking-tight">{word}</span>
            <span className="block text-[10px] uppercase tracking-[0.22em] text-ink/45">{sub}</span>
          </span>
        </Link>
        <nav className="hidden lg:flex items-center gap-1 text-[13px] text-ink/60">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-full px-2.5 py-1 hover:text-pine ${pathname === item.href ? "text-pine bg-white/40" : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <Link
            href={swapLocale(pathname, locale)}
            className="rounded-full border border-pine/25 px-2.5 py-1 uppercase tracking-wider text-[11px] text-pine"
          >
            {otherLocale(locale)}
          </Link>
          {user ? (
            <button onClick={logout} className="hidden sm:block text-ink/50 hover:text-ink px-2">
              {user.full_name}
            </button>
          ) : (
            <Link href={link("/login")} className="btn-ice text-sm !py-1.5 !px-4">
              {m.navLogin}
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}

function Footer({ locale }: { locale: Locale }) {
  const m = t(locale);
  return (
    <footer className="mt-20 px-4">
      <div className="glass-strong mx-auto max-w-6xl rounded-frost px-6 py-8 text-sm text-ink/50">
        <span className="font-semibold text-pine">ANYQ · АНЫҚ</span>
        <span className="mx-3">—</span>
        {m.footer}
      </div>
    </footer>
  );
}

function CompareBar({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { ids } = useCompare();
  if (ids.length === 0) return null;
  return (
    <div className="fixed bottom-4 inset-x-0 z-40 px-4">
      <div className="l3 mx-auto max-w-6xl rounded-full px-5 py-3 flex items-center justify-between text-sm">
        <span>
          {ids.length} {m.compareBar}
        </span>
        <Link href={`/${locale}/compare?ids=${ids.join(",")}`} className="text-pine underline">
          {m.compareOpen}
        </Link>
      </div>
    </div>
  );
}

export function AppShell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <AuthProvider>
      <CompareProvider>
        <Header locale={locale} />
        <main className="mx-auto max-w-6xl px-4 py-8 pb-24">{children}</main>
        <Footer locale={locale} />
        <CompareBar locale={locale} />
      </CompareProvider>
    </AuthProvider>
  );
}
