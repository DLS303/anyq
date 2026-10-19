import Link from "next/link";
import { fetchMaterials, fetchSpecialists } from "@/lib/api";
import { MATERIAL_CAT, CATEGORY, money, ratingLabel, reviewsLabel } from "@/lib/format";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";
import { PILOT_MODE } from "@/lib/pilot";
import { PhotoView } from "@/components/media/PhotoView";
import { HomeStage } from "@/components/home/HomeStage";
import { HomeRise } from "@/components/home/HomeRise";
import {
  ArrowRight,
  CheckCircle2,
  Layers,
  ShieldCheck,
  Truck,
} from "lucide-react";

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = (raw === "kk" ? "kk" : "ru") as Locale;
  const m = t(locale);
  const specialists = PILOT_MODE ? [] : await fetchSpecialists().catch(() => []);
  const materials = PILOT_MODE ? [] : await fetchMaterials().catch(() => []);

  return (
    <div className="grid grid-cols-1">
      <HomeStage locale={locale} />
      <HomeRise />

      <div className="home-flow relative z-20">
        <div
          className="home-veil pointer-events-none ml-[calc(50%-50vw)] mr-[calc(50%-50vw)] w-screen"
          aria-hidden
        />
        <div className="relative">
          <div
            className="pointer-events-none absolute inset-0 -z-10 ml-[calc(50%-50vw)] mr-[calc(50%-50vw)] w-screen bg-[#f8fafc]"
            aria-hidden
          />
          <div className="grid gap-12 pt-6 sm:gap-16 sm:pt-10">
      {PILOT_MODE ? null : (
      <>
      {/* Materials Showcase with Quick Action Buttons */}
      <section className="home-rise">
        <div className="flex items-end justify-between mb-5">
          <div>
            <p className="text-xs uppercase tracking-wider text-pine font-bold flex items-center gap-1.5">
              <Truck className="h-4 w-4" />
              <span>Прямые поставки от заводов</span>
            </p>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 mt-1">{m.navMaterials}</h2>
          </div>
          <Link
            href={`/${locale}/materials`}
            className="text-xs font-bold text-pine hover:underline flex items-center gap-1 bg-white px-3 py-1.5 rounded-full border border-slate-200 shadow-2xs"
          >
            <span>Все материалы</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="grid sm:grid-cols-3 gap-5">
          {materials.slice(0, 3).map((item) => (
            <div
              key={item.id}
              className="glass-strong rounded-3xl overflow-hidden shadow-luxury hover:shadow-luxury-lg transition-all flex flex-col justify-between group border border-slate-200/90"
            >
              <Link href={`/${locale}/materials/${item.slug}`} className="block">
                {item.photo ? (
                  <PhotoView
                    src={item.photo}
                    alt=""
                    sizes="(max-width: 640px) 100vw, 33vw"
                    className="h-44 w-full object-cover transition-transform duration-300 group-hover:scale-102"
                  />
                ) : (
                  <div className="h-44 bg-slate-100 grid place-items-center text-slate-400">
                    <Layers className="h-10 w-10 opacity-30" />
                  </div>
                )}
                <div className="p-5">
                  <span className="pill text-[10px] text-slate-600">{MATERIAL_CAT[item.category][locale]}</span>
                  <p className="text-lg font-bold text-slate-900 mt-2 line-clamp-1">{locale === "kk" ? item.title_kk : item.title_ru}</p>
                  <p className="text-xl font-bold text-pine mt-1.5">
                    {money(item.price_kzt, locale)} <span className="text-xs font-normal text-slate-500">/ {item.unit}</span>
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {item.city} · склад {item.stock} {item.unit}
                  </p>
                </div>
              </Link>
              <div className="px-5 pb-5 pt-1">
                <Link
                  href={`/${locale}/materials/${item.slug}`}
                  className="btn-ice w-full text-xs font-semibold !py-2"
                >
                  Заказать на объект
                </Link>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Specialists Showcase with Quick Action Buttons */}
      <section className="home-rise">
        <div className="flex items-end justify-between mb-5">
          <div>
            <p className="text-xs uppercase tracking-wider text-pine font-bold flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              <span>Лицензированные подрядчики</span>
            </p>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 mt-1">{m.navSpecialists}</h2>
          </div>
          <Link
            href={`/${locale}/specialists`}
            className="text-xs font-bold text-pine hover:underline flex items-center gap-1 bg-white px-3 py-1.5 rounded-full border border-slate-200 shadow-2xs"
          >
            <span>Весь реестр</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="grid sm:grid-cols-3 gap-5">
          {specialists.slice(0, 3).map((s) => (
            <div
              key={s.id}
              className="glass-strong rounded-3xl p-6 shadow-luxury hover:shadow-luxury-lg transition-all border border-slate-200/90 flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="pill text-[10px] text-slate-600">{CATEGORY[s.category][locale]}</span>
                  <span className="flex items-center gap-1 text-xs font-bold text-amber-600">
                    {s.reviews_count ? `★ ${ratingLabel(s.rating, s.reviews_count)}` : ratingLabel(s.rating, s.reviews_count)}
                  </span>
                </div>
                <h3 className="text-xl font-bold text-slate-900 group-hover:text-pine transition-colors">
                  {locale === "kk" ? s.company_kk : s.company_ru}
                </h3>
                <p className="text-xs text-slate-500 mt-1">{s.city} · {reviewsLabel(s.reviews_count)}</p>
                {s.license_verified ? (
                  <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-800 text-[11px] font-semibold border border-emerald-200/60">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    <span>Лицензия {s.license_cat}</span>
                  </div>
                ) : null}
              </div>

              <div className="mt-6 pt-4 border-t border-slate-100 flex items-center gap-2">
                <Link
                  href={`/${locale}/specialists/${s.slug}`}
                  className="btn-ice flex-1 text-xs font-semibold !py-2 text-center"
                >
                  Заказать услугу
                </Link>
                <Link
                  href={`/${locale}/specialists/${s.slug}`}
                  className="btn-ghost text-xs font-medium !py-2 !px-3"
                >
                  Профиль
                </Link>
              </div>
            </div>
          ))}
        </div>
      </section>
      </>
      )}

      {/* Enterprise Standards & Trust Banner */}
      <section className="home-rise bg-gradient-to-br from-slate-900 to-pine text-white rounded-3xl p-8 sm:p-10 shadow-2xl">
        <div className="grid md:grid-cols-3 gap-6 text-center sm:text-left">
          <div>
            <p className="text-3xl font-bold text-emerald-400">BOQ</p>
            <p className="text-sm font-semibold mt-1">Автосмета по объекту</p>
            <p className="text-xs text-slate-400 mt-1">Объёмы, работы, материалы и накладные в одной смете</p>
          </div>
          <div>
            <p className="text-3xl font-bold text-sky-400">CRM</p>
            <p className="text-sm font-semibold mt-1">Сделки и счета</p>
            <p className="text-xs text-slate-400 mt-1">Лиды, подряд, поставки и акты в одной карточке</p>
          </div>
          <div>
            <p className="text-3xl font-bold text-amber-300">КС-2</p>
            <p className="text-sm font-semibold mt-1">Площадка и контроль</p>
            <p className="text-xs text-slate-400 mt-1">Гант, журнал работ и акты КС-2/КС-3</p>
          </div>
        </div>
      </section>
          </div>
        </div>
      </div>
    </div>
  );
}
