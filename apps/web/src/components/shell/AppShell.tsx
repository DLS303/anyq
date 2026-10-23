"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, useState, useRef } from "react";
import { AuthProvider, useAuth } from "@/lib/auth";
import { FeatureProvider } from "@/lib/useFeature";
import { CompareProvider } from "@/lib/compare";
import type { Locale, Role } from "@/lib/types";
import { t } from "@/i18n/messages";
import { DEMO_MODE } from "@/lib/features";
import { PILOT_MODE } from "@/lib/pilot";
import { registerLink } from "@/lib/registration";
import { LuxuryNavTabs } from "./LuxuryNavTabs";
import { LuxuryProgressBar } from "./LuxuryProgressBar";
import { PageTransition } from "./PageTransition";
import {
  Building2,
  Calculator,
  HardHat,
  Layers,
  MessageSquare,
  User as UserIcon,
  LogOut,
  ChevronDown,
  CheckCircle2,
  X,
  Briefcase,
  SlidersHorizontal,
} from "lucide-react";

function otherLocale(locale: Locale): Locale {
  return locale === "ru" ? "kk" : "ru";
}

function swapLocale(pathname: string, locale: Locale) {
  const next = otherLocale(locale);
  return pathname.replace(/^\/(ru|kk)/, `/${next}`) || `/${next}`;
}

function navItems(locale: Locale, m: ReturnType<typeof t>, role?: Role) {
  const link = (path: string) => `/${locale}${path}`;
  const objects = { href: link("/site"), label: m.navObjects, icon: Building2 };
  const estimates = { href: link("/estimates"), label: m.navEstimates, icon: Calculator };
  const cabinet = { href: link("/cabinet"), label: m.navCabinet, icon: UserIcon };
  const chat = { href: link("/chat"), label: m.navChat, icon: MessageSquare };
  const crm = { href: link("/crm"), label: m.navCrm, icon: Briefcase };
  const materials = { href: link("/materials"), label: m.navMaterials, icon: Layers };
  const moderation = { href: link("/moderation"), label: m.navModeration, icon: SlidersHorizontal };
  if (!DEMO_MODE) {
    if (role === "moderator") return [moderation, objects, chat, cabinet];
    if (role === "supplier") return [materials, objects, chat, cabinet];
    if (role === "owner" || role === "admin") return [crm, objects, estimates, chat, cabinet, ...(role === "admin" ? [moderation] : [])];
    return [objects, estimates, chat, cabinet];
  }
  if (PILOT_MODE) {
    const field = role === "contractor" || role === "supervisor";
    if (field) return [objects, estimates, chat, cabinet];
    if (role === "owner" || role === "admin") return [crm, objects, estimates, chat, cabinet];
    return [estimates, objects, chat, cabinet];
  }
  return [
    { href: link("/crm"), label: m.navCrm, icon: Briefcase },
    materials,
    { href: link("/estimates"), label: m.navAutoEstimate, icon: Calculator },
    { href: link("/specialists"), label: m.navSpecialists, icon: HardHat },
    { href: link("/site"), label: m.navSite, icon: Building2 },
    { href: link("/catalog"), label: m.navCatalog, icon: Layers },
    { href: link("/control"), label: m.navPanel, icon: SlidersHorizontal },
    chat,
    cabinet,
  ];
}

function Header({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const link = (path: string) => `/${locale}${path}`;
  const nav = navItems(locale, m, user?.role);
  const showCrm = DEMO_MODE ? !PILOT_MODE || user?.role === "owner" || user?.role === "admin" : user?.role === "owner" || user?.role === "admin";
  const signupHref = registerLink(locale);
  const [open, setOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setOpen(false);
    setUserMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const word = locale === "kk" ? "АНЫҚ" : "ANYQ";

  return (
    <header className="anyq-header sticky top-0 z-40 pt-[max(0.5rem,env(safe-area-inset-top))] px-3">
      <div className="glass mx-auto flex min-w-0 max-w-6xl items-center gap-2.5 rounded-full px-3 py-2 sm:px-4 shadow-luxury">
        {/* Mobile menu hamburger */}
        <button
          type="button"
          className="lg:hidden grid h-10 w-10 place-items-center rounded-full text-pine hover:bg-slate-100 transition-colors"
          aria-label={m.navMenu}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="flex flex-col gap-1.5">
            <span className={`block h-0.5 w-4.5 bg-pine transition-transform duration-300 ${open ? "translate-y-2 rotate-45" : ""}`} />
            <span className={`block h-0.5 w-4.5 bg-pine transition-opacity duration-300 ${open ? "opacity-0" : ""}`} />
            <span className={`block h-0.5 w-4.5 bg-pine transition-transform duration-300 ${open ? "-translate-y-2 -rotate-45" : ""}`} />
          </span>
        </button>

        {/* Brand Logo */}
        <Link href={link("")} className="flex items-center gap-2.5 shrink-0 group">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-pine to-ice text-[11px] font-bold tracking-[0.14em] text-white shadow-navy group-hover:scale-105 transition-transform">
            AQ
          </span>
          <span className="leading-tight">
            <span className="block text-[17px] font-bold tracking-tight text-pine flex items-center gap-1.5">
              {word}
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            </span>
            <span className="hidden xs:block text-[9px] uppercase tracking-[0.25em] text-slate-500 font-semibold">
              PREMIUM PROPTECH
            </span>
          </span>
        </Link>

        {/* Luxury Desktop Nav with sliding glass capsule and haptic physics */}
        <LuxuryNavTabs items={nav} />

        {/* Right side actions */}
        <div className="ml-auto flex items-center gap-2 text-sm">
          {/* Language Switch */}
          <Link
            href={swapLocale(pathname, locale)}
            className="grid h-9 min-w-9 place-items-center rounded-full border border-slate-300 px-2 uppercase tracking-wider text-[11px] font-bold text-pine hover:bg-white transition-colors"
          >
            {otherLocale(locale)}
          </Link>

          {/* User Auth or Menu */}
          {user ? (
            <div className="relative" ref={userMenuRef}>
              <button
                type="button"
                onClick={() => setUserMenuOpen((v) => !v)}
                className="flex min-w-0 items-center gap-2 pl-2.5 pr-3 py-1 rounded-full bg-white border border-slate-200 shadow-xs hover:border-slate-300 transition-all text-xs font-medium text-slate-700 max-w-[7.5rem] sm:max-w-[11rem]"
              >
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                <span className="truncate">{user.full_name}</span>
                <ChevronDown className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              </button>

              {userMenuOpen && (
                <div className="absolute right-0 mt-2 w-56 rounded-2xl bg-white p-2 shadow-2xl border border-slate-100 animate-fadeIn z-50">
                  <div className="px-3 py-2 border-b border-slate-100">
                    <p className="text-xs font-semibold text-slate-900 truncate">{user.full_name}</p>
                    <p className="text-[11px] text-slate-500 capitalize">{user.role} · {user.email}</p>
                  </div>
                  <div className="grid gap-1 py-1 text-xs">
                    <Link
                      href={link("/cabinet")}
                      onClick={() => setUserMenuOpen(false)}
                      className="px-3 py-2 rounded-xl text-slate-700 hover:bg-slate-50 flex items-center gap-2 font-medium"
                    >
                      <UserIcon className="h-4 w-4 text-slate-500" />
                      {m.navCabinet}
                    </Link>
                    {showCrm ? (
                      <Link
                        href={link("/crm")}
                        onClick={() => setUserMenuOpen(false)}
                        className="px-3 py-2 rounded-xl text-slate-700 hover:bg-slate-50 flex items-center gap-2 font-medium"
                      >
                        <Briefcase className="h-4 w-4 text-slate-500" />
                        {m.navCrm}
                      </Link>
                    ) : null}
                    <Link
                      href={link("/chat")}
                      onClick={() => setUserMenuOpen(false)}
                      className="px-3 py-2 rounded-xl text-slate-700 hover:bg-slate-50 flex items-center gap-2 font-medium"
                    >
                      <MessageSquare className="h-4 w-4 text-slate-500" />
                      {m.navChat}
                    </Link>
                    <button
                      type="button"
                      onClick={() => {
                        logout();
                        setUserMenuOpen(false);
                      }}
                      className="w-full text-left px-3 py-2 rounded-xl text-red-600 hover:bg-red-50 flex items-center gap-2 font-medium"
                    >
                      <LogOut className="h-4 w-4 text-red-500" />
                      {m.navLogout}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <Link href={signupHref ?? link("/login")} className="btn-ice text-xs !py-1.5 !px-4 !min-h-9 font-semibold">
              {signupHref ? m.register : m.navLogin}
            </Link>
          )}
        </div>
      </div>

      {/* Mobile Drawer */}
      {open ? (
        <div className="lg:hidden fixed inset-0 z-50">
          <button type="button" className="absolute inset-0 bg-slate-950/40 backdrop-blur-xs" aria-label={m.navClose} onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-[min(88vw,340px)] bg-white shadow-2xl p-5 pt-[max(1.25rem,env(safe-area-inset-top))] overflow-y-auto">
            <div className="flex items-center justify-between mb-6 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-pine text-white text-xs font-bold">AQ</span>
                <span className="font-bold text-base text-pine">{word}</span>
              </div>
              <button type="button" onClick={() => setOpen(false)} className="p-1 rounded-full text-slate-500">
                <X className="h-5 w-5" />
              </button>
            </div>

            <nav className="grid gap-1.5 text-sm">
              {PILOT_MODE ? null : (
                <Link
                  href={link("")}
                  className={`rounded-xl px-3.5 py-2.5 font-medium flex items-center gap-2.5 ${
                    pathname === link("") ? "bg-pine text-white font-semibold" : "text-slate-700 hover:bg-slate-50"
                  }`}
                  onClick={() => setOpen(false)}
                >
                  {m.navHome}
                </Link>
              )}
              {nav.map((item) => {
                const Icon = item.icon;
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={`rounded-xl px-3.5 py-2.5 font-medium flex items-center gap-2.5 ${
                      active ? "bg-pine text-white font-semibold" : "text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>

            <div className="mt-6">
              {user ? (
                <button
                  type="button"
                  className="w-full rounded-xl border border-red-200 text-red-600 font-medium py-2.5 text-sm hover:bg-red-50"
                  onClick={() => {
                    logout();
                    setOpen(false);
                  }}
                >
                  {m.navLogout} · {user.full_name}
                </button>
              ) : (
                <Link href={signupHref ?? link("/login")} className="btn-ice w-full text-center font-semibold" onClick={() => setOpen(false)}>
                  {signupHref ? m.register : m.navLogin}
                </Link>
              )}
            </div>
          </div>
        </div>
      ) : null}

    </header>
  );
}

function RouteWash() {
  const pathname = usePathname();
  const prev = useRef(pathname);
  const [show, setShow] = useState(false);

  useLayoutEffect(() => {
    if (prev.current === pathname) return;
    prev.current = pathname;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (typeof document.startViewTransition === "function") return;
    setShow(true);
    const id = window.setTimeout(() => setShow(false), 760);
    return () => window.clearTimeout(id);
  }, [pathname]);

  if (!show) return null;
  return <div className="route-wash" aria-hidden onAnimationEnd={() => setShow(false)} />;
}

function GlobalToast() {
  const [toast, setToast] = useState<{ message: string } | null>(null);

  useEffect(() => {
    function onToast(e: Event) {
      const detail = (e as CustomEvent<{ message: string }>).detail;
      if (detail?.message) {
        setToast({ message: detail.message });
        setTimeout(() => setToast(null), 3800);
      }
    }
    window.addEventListener("anyq-toast", onToast);
    return () => window.removeEventListener("anyq-toast", onToast);
  }, []);

  if (!toast) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 animate-fadeIn">
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-2xl bg-slate-900 text-white text-xs font-semibold shadow-2xl border border-slate-800">
        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
        <span>{toast.message}</span>
      </div>
    </div>
  );
}

function Footer({ locale }: { locale: Locale }) {
  const m = t(locale);
  return (
    <footer className="mt-20 px-4 mb-20 lg:mb-0">
      <div className="glass-strong mx-auto max-w-6xl rounded-3xl p-6 sm:p-8 text-sm text-slate-500 shadow-luxury border border-slate-200/90">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-6 border-b border-slate-200/70">
          <div className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-pine text-white text-xs font-bold shadow-navy">
              AQ
            </span>
            <div>
              <span className="font-bold text-slate-900 text-base">ANYQ · АНЫҚ</span>
              <p className="text-xs text-slate-400">{m.footerNote}</p>
            </div>
          </div>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-slate-500">{m.footer}</p>
        <p className="mt-2 text-xs">
          <Link href={`/${locale}/legal/privacy`} className="underline text-slate-600 hover:text-slate-900">
            {m.privacy}
          </Link>
          <span className="mx-2 text-slate-300">·</span>
          <Link href={`/${locale}/legal/pd-consent`} className="underline text-slate-600 hover:text-slate-900">
            {m.pdConsent}
          </Link>
        </p>
      </div>
    </footer>
  );
}

function BottomNav({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();
  const pathname = usePathname();
  const onProject = /\/site\/[^/]+/.test(pathname);
  const items = !DEMO_MODE || PILOT_MODE
    ? navItems(locale, m, user?.role).map((item) => ({
        href: item.href,
        label: item.label,
        match: (p: string) => p === item.href || p.startsWith(`${item.href}/`),
      }))
    : [
        { href: `/${locale}`, label: m.navHome, match: (p: string) => p === `/${locale}` },
        { href: `/${locale}/crm`, label: m.navCrm, match: (p: string) => p.includes("/crm") },
        { href: `/${locale}/materials`, label: m.navMaterials, match: (p: string) => p.includes("/materials") },
        { href: `/${locale}/estimates`, label: m.navEstimates, match: (p: string) => p.includes("/estimates") },
        { href: `/${locale}/cabinet`, label: m.navCabinet, match: (p: string) => p.includes("/cabinet") || p.includes("/login") },
      ];
  return (
    <nav className={`anyq-tabbar lg:hidden fixed bottom-0 inset-x-0 z-40 border-t border-slate-200/80 bg-white/95 backdrop-blur-md pb-[env(safe-area-inset-bottom)] shadow-luxury ${(!DEMO_MODE || PILOT_MODE) && onProject ? "max-sm:hidden" : ""}`}>
      <div className="grid" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {items.map((item) => {
          const on = item.match(pathname);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center min-h-14 gap-1 text-[10px] leading-tight px-1 transition-colors ${
                on ? "text-pine font-bold" : "text-slate-500"
              }`}
            >
              <span className={`h-1 w-6 rounded-full transition-all ${on ? "bg-pine" : "bg-transparent"}`} />
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export function AppShell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <AuthProvider>
      <FeatureProvider>
      <CompareProvider>
        <LuxuryProgressBar />
        <Header locale={locale} />
        <main className="mx-auto max-w-6xl px-4 py-6 pb-28 lg:pb-12">
          <PageTransition>{children}</PageTransition>
        </main>
        <Footer locale={locale} />
        <BottomNav locale={locale} />
        <RouteWash />
        <GlobalToast />
      </CompareProvider>
      </FeatureProvider>
    </AuthProvider>
  );
}
