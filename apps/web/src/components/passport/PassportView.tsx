"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { sendInquiry, toggleFavorite } from "@/lib/api";
import type { DevCalc, Locale, Plot, Utility } from "@/lib/types";
import { PURPOSE, RELIEF, STATUS, UTILITY, descOf, maskCadastral, money, titleOf } from "@/lib/format";
import { t } from "@/i18n/messages";
import { AuthImage } from "@/components/media/AuthImage";

const PlotMap = dynamic(() => import("@/components/catalog/PlotMap"), { ssr: false });
const CadastralGeoPlanner = dynamic(
  () => import("@/components/passport/CadastralGeoPlanner").then((mod) => mod.CadastralGeoPlanner),
  { ssr: false }
);

function Util({ label, value, locale }: { label: string; value: Utility; locale: Locale }) {
  const tone =
    value === "connected"
      ? "bg-pine text-paper"
      : value === "absent"
        ? "bg-mist text-ink/50"
        : "bg-sand/40 text-ink";
  return (
    <div className="border border-ink/10 p-3">
      <p className="text-[11px] uppercase tracking-wider text-ink/45">{label}</p>
      <p className={`mt-2 inline-block px-2 py-0.5 text-xs ${tone}`}>{UTILITY[value][locale]}</p>
    </div>
  );
}

function Flag({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`text-xs px-2 py-1 border ${on ? "border-clay text-clay" : "border-ink/10 text-ink/40"}`}>
      {label}
      {on ? "" : " — нет"}
    </span>
  );
}

export function PassportView({
  plot,
  locale,
  calc,
  favorite: fav0,
}: {
  plot: Plot;
  locale: Locale;
  calc?: DevCalc;
  favorite?: boolean;
}) {
  const m = t(locale);
  const { user } = useAuth();
  const [fav, setFav] = useState(Boolean(fav0));
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function onFav() {
    if (!user) {
      setError(m.needLoginFav);
      return;
    }
    const res = await toggleFavorite(user.email, plot.id);
    setFav(res.favorite);
  }

  async function onInquiry(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    try {
      await sendInquiry(
        plot.id,
        {
          name: String(fd.get("name") || user?.full_name || ""),
          phone: String(fd.get("phone") || user?.phone || ""),
          message: String(fd.get("message") || ""),
        },
        user?.email,
      );
      setSent(true);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    }
  }

  const docs = plot.docs ?? { egrn: false, topo: false, apz: false, tu: false };

  return (
    <div className="grid gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-wider text-ink/45">
            {m.passport} · {PURPOSE[plot.purpose][locale]}
          </p>
          <h1 className="font-serif text-4xl mt-1">{titleOf(plot, locale)}</h1>
          <p className="mt-2 text-ink/60">{plot.district}</p>
        </div>
        <div className="text-right">
          <p className="font-serif text-3xl">{money(plot.price_kzt, locale)}</p>
          <p className="text-sm text-ink/55">
            {plot.area_sotka} {m.sotka}
          </p>
          <button onClick={onFav} className="mt-3 text-sm underline">
            {fav ? m.unfavorite : m.favorite}
          </button>
        </div>
      </div>

      {plot.photos?.length ? (
        <div className="grid sm:grid-cols-2 gap-2">
          {plot.photos.map((src) => (
            <AuthImage key={src} src={src} alt="" className="h-56 w-full object-cover border border-ink/10" />
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2 text-xs uppercase tracking-wider">
        {plot.verified ? (
          <span className="bg-pine text-paper px-2 py-1">{m.verified}</span>
        ) : (
          <span className="border border-ink/20 px-2 py-1">{m.unverified}</span>
        )}
        <span className="border border-ink/10 px-2 py-1">
          {m.trust} {plot.trust_score}
        </span>
        <span className="border border-ink/10 px-2 py-1">{STATUS[plot.status][locale]}</span>
        {plot.divisible ? <span className="border border-ink/10 px-2 py-1">{m.divisible}</span> : null}
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="h-[360px] border border-ink/10 overflow-hidden">
          <PlotMap plots={[plot]} locale={locale} />
        </div>
        <div className="border border-ink/10 bg-white/50 p-5">
          <h2 className="font-serif text-2xl">{m.legal}</h2>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <dt className="text-ink/45">{m.cadastral}</dt>
            <dd>{maskCadastral(plot.cadastral_no, plot.verified)}</dd>
            <dt className="text-ink/45">{m.area}</dt>
            <dd>
              {plot.area_sotka} {m.sotka}
            </dd>
            <dt className="text-ink/45">{m.purpose}</dt>
            <dd>{PURPOSE[plot.purpose][locale]}</dd>
            <dt className="text-ink/45">{m.landCategory}</dt>
            <dd>{plot.land_category}</dd>
            <dt className="text-ink/45">{m.relief}</dt>
            <dd>{RELIEF[plot.relief ?? "flat"][locale]}</dd>
            <dt className="text-ink/45">{m.soil}</dt>
            <dd>{plot.soil || "—"}</dd>
            <dt className="text-ink/45">{m.encumbrances}</dt>
            <dd>{plot.encumbrances || "нет"}</dd>
          </dl>
          <p className="mt-4 text-sm leading-relaxed">{descOf(plot, locale)}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Flag on={plot.red_lines} label={m.redLines} />
            <Flag on={plot.power_protection_zone} label={m.powerZone} />
            <Flag on={plot.gas_protection_zone} label={m.gasZone} />
            <Flag on={plot.water_protection} label={m.waterZone} />
            <Flag on={plot.registered_buildings} label={m.buildings} />
          </div>
          <p className="mt-4 text-xs text-ink/45">{m.govStub}</p>
      </div>
      </div>

      <section className="mt-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <span className="text-[11px] uppercase tracking-wider text-pine font-semibold">Turf.js & GIS Spatial Engine</span>
            <h2 className="font-serif text-2xl">
              {locale === "kk"
                ? "Кадастрлық гео-калькулятор және СНиП үйді орналастыру"
                : "Кадастровый гео-калькулятор и посадка дома по СНиП РК"}
            </h2>
          </div>
          <span className="text-xs text-ink/50 hidden sm:inline">СП РК 3.01-101-2013</span>
        </div>
        <CadastralGeoPlanner plot={plot} locale={locale} />
      </section>

      <section>
        <h2 className="font-serif text-2xl mb-3">{m.infra}</h2>
        <div className="grid sm:grid-cols-5 gap-2">
          <Util label={m.electricity} value={plot.electricity} locale={locale} />
          <Util label={m.gas} value={plot.gas} locale={locale} />
          <Util label={m.water} value={plot.water} locale={locale} />
          <Util label={m.sewage} value={plot.sewage} locale={locale} />
          <Util label={m.road} value={plot.access_road} locale={locale} />
        </div>
      </section>

      <section className="border border-dashed border-ink/20 p-5">
        <h2 className="font-serif text-2xl">{m.docs}</h2>
        <p className="text-sm text-ink/60 mt-2">{m.docsHint}</p>
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          <Flag on={docs.egrn} label={m.docEgrn} />
          <Flag on={docs.topo} label={m.docTopo} />
          <Flag on={docs.apz} label={m.docApz} />
          <Flag on={docs.tu} label={m.docTu} />
        </div>
      </section>

      {calc ? (
        <section className="border border-ink/10 bg-white/50 p-5">
          <h2 className="font-serif text-2xl">{m.calcTitle}</h2>
          <dl className="mt-4 grid sm:grid-cols-2 gap-2 text-sm">
            <dt className="text-ink/45">{m.calcUtils}</dt>
            <dd>{money(calc.utils_kzt, locale)}</dd>
            <dt className="text-ink/45">{m.calcFence}</dt>
            <dd>{money(calc.fence_kzt, locale)}</dd>
            <dt className="text-ink/45">{m.calcFoundation}</dt>
            <dd>{money(calc.foundation_kzt, locale)}</dd>
            <dt className="font-medium">{m.calcTotal}</dt>
            <dd className="font-medium">{money(calc.total_kzt, locale)}</dd>
          </dl>
          <p className="mt-3 text-xs text-ink/45">{calc.disclaimer}</p>
        </section>
      ) : null}

      <section className="border border-ink/10 p-5">
        <h2 className="font-serif text-2xl mb-2">{m.navSpecialists}</h2>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link href={`/${locale}/specialists?`} className="underline">
            {m.navSpecialists}
          </Link>
          <Link href={`/${locale}/specialists`} className="underline">
            изыскания / проект / СМР
          </Link>
          <Link href={`/${locale}/materials`} className="underline">
            {m.navMaterials}
          </Link>
          {plot.id === "p-besagash" || plot.slug === "izhs-besagash-gaz" ? (
            <Link href={`/${locale}/site/pr-besagash`} className="underline">
              {m.navSite}
            </Link>
          ) : null}
        </div>
      </section>

      <section className="border border-ink/10 p-5">
        <h2 className="font-serif text-2xl">{m.inquiry}</h2>
        {sent ? (
          <div className="mt-3 p-4 bg-emerald-50/70 border border-emerald-200 rounded-lg">
            <p className="text-emerald-900 font-medium">✓ {m.inquirySent}</p>
            <p className="text-xs text-emerald-800/70 mt-1">
              Заявка зарегистрирована в CRM и создан лид. С вами свяжется ответственный менеджер.
            </p>
            <div className="mt-3 flex items-center gap-3 text-xs">
              <Link href={`/${locale}/crm`} className="text-pine font-semibold underline">
                Открыть в CRM →
              </Link>
              <span className="text-ink/30">•</span>
              <Link href={`/${locale}/chat`} className="text-pine font-semibold underline">
                Перейти в чат →
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={onInquiry} className="mt-4 grid gap-3 max-w-md">
            <input
              name="name"
              required
              placeholder={m.name}
              defaultValue={user?.full_name ?? ""}
              className="border border-ink/15 px-3 py-2"
            />
            <input
              name="phone"
              required
              placeholder={m.phone}
              defaultValue={user?.phone ?? ""}
              className="border border-ink/15 px-3 py-2"
            />
            <textarea name="message" rows={3} placeholder={m.message} className="border border-ink/15 px-3 py-2" />
            <button className="bg-pine text-paper py-2">{m.sendInquiry}</button>
          </form>
        )}
        {error ? <p className="text-clay text-sm mt-2">{error}</p> : null}
        {!user ? (
          <p className="text-xs text-ink/45 mt-2">
            <Link href={`/${locale}/login`} className="underline">
              {m.navLogin}
            </Link>
          </p>
        ) : null}
      </section>
    </div>
  );
}
