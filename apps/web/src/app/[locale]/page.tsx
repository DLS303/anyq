import Link from "next/link";
import { fetchMaterials, fetchModules, fetchPlots, fetchSpecialists } from "@/lib/api";
import { MATERIAL_CAT, CATEGORY } from "@/lib/format";
import { PlotCard } from "@/components/plots/PlotCard";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = (raw === "kk" ? "kk" : "ru") as Locale;
  const m = t(locale);
  const plots = await fetchPlots().catch(() => []);
  const modules = await fetchModules().catch(() => []);
  const specialists = await fetchSpecialists().catch(() => []);
  const materials = await fetchMaterials().catch(() => []);
  const mark = locale === "kk" ? "АНЫҚ" : "ANYQ";

  return (
    <div className="grid gap-16">
      <section className="relative overflow-hidden rounded-[28px] min-h-[440px] border border-pine/15">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/design/almaty-aerial.jpg" alt="" className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#efe8de]/90 via-[#efe8de]/55 to-transparent" />
        <div className="relative z-10 grid md:grid-cols-[1.15fr_0.85fr] gap-8 p-8 md:p-12 items-end min-h-[440px]">
          <div>
            <p className="text-[12px] uppercase tracking-[0.18em] text-ink/50">
              {locale === "kk" ? "жер → анықтық → әрекет → ақша → құрылыс" : "земля → ясность → действие → деньги → стройка"}
            </p>
            <p className="mt-3 text-sm font-semibold tracking-tight text-pine">{mark}</p>
            <h1 className="mt-2 text-[40px] leading-[1.15] tracking-[-0.02em] font-medium md:text-5xl">{m.heroTitle}</h1>
            <p className="mt-4 max-w-xl text-[17px] leading-7 text-ink/60">{m.heroLead}</p>
            <div className="mt-6 flex flex-wrap gap-2 text-[12px] tracking-wide">
              {["Земля", "Ясность", "Действие", "Деньги"].map((n) => (
                <span key={n} className="glass rounded-full px-3 py-1.5">
                  {n}
                </span>
              ))}
              <span className="glass rounded-full px-3 py-1.5 opacity-45">Стройка</span>
            </div>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href={`/${locale}/catalog`} className="btn-ice">
                {m.ctaCatalog}
              </Link>
              <Link href={`/${locale}/plots/izhs-besagash-gaz`} className="btn-ghost">
                {m.navPassport}
              </Link>
            </div>
          </div>
          <div className="glass-strong rounded-frost p-6">
            <p className="text-pine text-xs uppercase tracking-[0.16em]">{m.modules}</p>
            <ul className="mt-4 grid gap-3 text-sm">
              {modules.map((mod) => (
                <li key={mod.id} className="flex justify-between gap-3 border-b border-ink/10 pb-2">
                  <span>{mod.title}</span>
                  <span className={mod.status === "live" ? "text-pine-2" : "text-ink/35"}>
                    {mod.status === "live" ? m.live : m.stub}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-medium tracking-tight mb-5">{m.pillarsTitle}</h2>
        <div className="grid md:grid-cols-3 gap-4">
          {[
            [m.p1, m.p1d],
            [m.p2, m.p2d],
            [m.p3, m.p3d],
          ].map(([title, desc]) => (
            <article key={title} className="glass-strong rounded-frost p-6">
              <h3 className="text-lg font-medium text-pine">{title}</h3>
              <p className="mt-2 text-[15px] leading-6 text-ink/60">{desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between mb-5">
          <h2 className="text-2xl font-medium tracking-tight">{m.navCatalog}</h2>
          <Link href={`/${locale}/catalog`} className="text-sm text-pine">
            {m.ctaCatalog}
          </Link>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {plots.slice(0, 3).map((plot) => (
            <PlotCard key={plot.id} plot={plot} locale={locale} />
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between mb-5">
          <h2 className="text-2xl font-medium tracking-tight">{m.navMaterials}</h2>
          <Link href={`/${locale}/materials`} className="text-sm text-pine">
            {m.navMaterials}
          </Link>
        </div>
        <div className="grid sm:grid-cols-3 gap-4 mb-12">
          {materials.slice(0, 3).map((item) => (
            <Link key={item.id} href={`/${locale}/materials/${item.slug}`} className="glass-strong rounded-frost overflow-hidden">
              {item.photo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={item.photo} alt="" className="h-32 w-full object-cover" />
              ) : null}
              <div className="p-4">
                <p className="text-[12px] tracking-wide text-ink/45">{MATERIAL_CAT[item.category][locale]}</p>
                <p className="text-lg font-medium mt-1">{locale === "kk" ? item.title_kk : item.title_ru}</p>
              </div>
            </Link>
          ))}
        </div>
        <div className="flex items-end justify-between mb-5">
          <h2 className="text-2xl font-medium tracking-tight">{m.navSpecialists}</h2>
          <Link href={`/${locale}/specialists`} className="text-sm text-pine">
            {m.navSpecialists}
          </Link>
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          {specialists.slice(0, 3).map((s) => (
            <Link key={s.id} href={`/${locale}/specialists/${s.slug}`} className="glass-strong rounded-frost p-5">
              <p className="text-[12px] tracking-wide text-ink/45">{CATEGORY[s.category][locale]}</p>
              <p className="text-lg font-medium mt-1">{locale === "kk" ? s.company_kk : s.company_ru}</p>
              <p className="text-sm mt-1 text-ink/55">★ {s.rating || "—"}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
