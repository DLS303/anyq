"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { createOrder } from "@/lib/api";
import { CATEGORY, money, ratingLabel, reviewsLabel } from "@/lib/format";
import type { Locale, Review, Specialist } from "@/lib/types";
import { PhotoView } from "@/components/media/PhotoView";
import { t } from "@/i18n/messages";
import { CheckCircle2, ShieldCheck, Star, MessageSquare, Briefcase, ExternalLink, X, Send } from "lucide-react";

export function SpecialistProfile({
  locale,
  specialist,
  reviews,
}: {
  locale: Locale;
  specialist: Specialist;
  reviews: Review[];
}) {
  const m = t(locale);
  const router = useRouter();
  const { user } = useAuth();
  const [message, setMessage] = useState("Здравствуйте! Требуется выезд на объект, консультация и расчет коммерческого предложения.");
  const [clientPhone, setClientPhone] = useState(user?.phone ?? "");
  const [clientName, setClientName] = useState(user?.full_name ?? "");
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [previewProject, setPreviewProject] = useState<{ title: string; photo?: string } | null>(null);

  async function order() {
    setBusy(true);
    setError("");
    try {
      if (!user) {
        window.dispatchEvent(
          new CustomEvent("anyq-toast", {
            detail: { message: "Сначала зарегистрируйте компанию для пилота Engicon" },
          }),
        );
        router.push(`/${locale}/login?mode=register`);
        return;
      }

      const o = await createOrder(user.email, specialist.id, {
        message: `${message}\nКонтакт: ${clientName}, ${clientPhone}`,
      });
      setDone(o.thread_id || o.id);

      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("anyq-toast", {
            detail: { message: `Заявка специалисту "${specialist.company_ru}" успешно создана!` },
          })
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка создания заказа");
    } finally {
      setBusy(false);
    }
  }

  const name = locale === "kk" ? specialist.company_kk : specialist.company_ru;
  const bio = locale === "kk" ? specialist.bio_kk : specialist.bio_ru;

  return (
    <div className="grid gap-8">
      {/* Top Banner & Order Section */}
      <div className="grid md:grid-cols-[1.2fr_0.8fr] gap-6">
        <div className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
          {specialist.cover ? (
            <PhotoView
              src={specialist.cover}
              alt=""
              sizes="(max-width: 640px) 100vw, 60vw"
              className="mb-6 h-48 w-full rounded-2xl border border-slate-200 object-cover shadow-xs sm:h-64"
            />
          ) : null}

          <div className="flex items-center gap-2 mb-2">
            <span className="pill text-[10px] text-slate-600">{CATEGORY[specialist.category][locale]}</span>
            {specialist.license_verified ? (
              <span className="pill text-[10px] text-emerald-800 bg-emerald-50 border-emerald-200 flex items-center gap-1 font-semibold">
                <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                <span>{m.licenseBadge.replace("{cat}", specialist.license_cat)}</span>
              </span>
            ) : null}
          </div>

          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900 mt-2">{name}</h1>
          <p className="mt-3 text-slate-600 text-sm sm:text-base leading-relaxed">{bio}</p>

          <div className="mt-5 flex flex-wrap items-center gap-4 text-xs font-semibold text-slate-600">
            <span className="flex items-center gap-1 text-amber-600 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
              <Star className="h-3.5 w-3.5 fill-amber-500 text-amber-500" />
              <span>{ratingLabel(specialist.rating, specialist.reviews_count)}</span>
            </span>
            <span>{reviewsLabel(specialist.reviews_count)}</span>
            <span>•</span>
            <span>{specialist.city}</span>
            {specialist.bin ? (
              <>
                <span>•</span>
                <span className="font-mono text-slate-400">БИН {specialist.bin}</span>
              </>
            ) : null}
          </div>
        </div>

        {/* Order / Inquiry Card */}
        <div className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90 h-fit">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-xl font-bold text-slate-900">Заказать услугу / КП</h2>
              <p className="text-xs text-slate-500 mt-0.5">Создает сделку в CRM и открывает защищенный чат</p>
            </div>
            <Briefcase className="h-6 w-6 text-pine" />
          </div>

          {done ? (
            <div className="mt-6 p-5 rounded-2xl bg-emerald-50 border border-emerald-200">
              <p className="text-sm font-bold text-emerald-900 flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                <span>Заявка успешно отправлена!</span>
              </p>
              <p className="text-xs text-emerald-800 mt-2 leading-relaxed">
                Специалист получил уведомление. Вы можете сразу перейти в диалог или отслеживать воронку в CRM.
              </p>
              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <Link href={`/${locale}/chat/${done}`} className="btn-ice !py-2 !px-4 text-xs font-semibold">
                  {m.navChat} →
                </Link>
                <Link href={`/${locale}/crm`} className="btn-ghost !py-2 !px-4 text-xs font-semibold">
                  {m.navCrm} →
                </Link>
              </div>
            </div>
          ) : (
            <div className="mt-5 grid gap-3">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                  Ваше имя
                </label>
                <input
                  type="text"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  placeholder="Имя заказчика"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                  Телефон для связи
                </label>
                <input
                  type="tel"
                  value={clientPhone}
                  onChange={(e) => setClientPhone(e.target.value)}
                  placeholder="+7 (701) 000-00-00"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                  ТЗ / Вопрос по объекту
                </label>
                <textarea
                  rows={3}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                />
              </div>

              <button
                type="button"
                onClick={order}
                disabled={busy}
                className="btn-ice w-full font-bold text-sm shadow-navy justify-center mt-2"
              >
                <Send className="h-4 w-4" />
                <span>{busy ? "Отправка..." : "Отправить заявку"}</span>
              </button>

              {error ? <p className="text-xs text-red-600 font-semibold">{error}</p> : null}

              <p className="text-[11px] text-slate-400 text-center">
                Заявка фиксируется в заказе. Оплата через сервис не проводится.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Pricing Section */}
      <section className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
        <h2 className="text-2xl font-bold text-slate-900 mb-4">{m.prices}</h2>
        <div className="grid gap-2.5">
          {specialist.prices.map((p) => (
            <div
              key={p.title_ru}
              className="flex justify-between items-center p-3.5 rounded-2xl bg-white border border-slate-100 shadow-2xs hover:border-slate-200 transition-colors"
            >
              <span className="font-semibold text-slate-800 text-sm">
                {locale === "kk" ? p.title_kk : p.title_ru} <span className="text-slate-400 font-normal">/ {p.unit}</span>
              </span>
              <span className="font-bold text-pine text-base">{money(p.price_kzt, locale)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Portfolio Section with Working Click-to-Preview Modal */}
      <section className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
        <h2 className="text-2xl font-bold text-slate-900 mb-4">{m.portfolio}</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          {specialist.portfolio.map((p) => (
            <button
              key={p.title_ru}
              type="button"
              onClick={() => setPreviewProject({ title: p.title_ru, photo: p.photo })}
              className="text-left rounded-2xl overflow-hidden border border-slate-200 bg-white shadow-2xs hover:shadow-luxury transition-all group"
            >
              {p.photo ? (
                <PhotoView
                  src={p.photo}
                  alt=""
                  sizes="(max-width: 640px) 100vw, 50vw"
                  className="h-44 w-full object-cover transition-transform duration-300 group-hover:scale-102"
                />
              ) : null}
              <div className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-slate-900">{p.title_ru}</p>
                  <p className="text-xs text-slate-400 mt-0.5">Нажмите для просмотра объекта</p>
                </div>
                <ExternalLink className="h-4 w-4 text-slate-400 group-hover:text-pine transition-colors" />
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Reviews Section */}
      <section className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
        <h2 className="text-2xl font-bold text-slate-900 mb-4">{m.reviews}</h2>
        {reviews.length === 0 ? <p className="text-slate-500 text-sm">{m.empty}</p> : null}
        <div className="grid gap-3">
          {reviews.map((r) => (
            <div key={r.id} className="p-4 rounded-2xl bg-white border border-slate-100 shadow-2xs">
              <div className="flex items-center gap-1 text-amber-500 text-sm font-bold">
                {"★".repeat(r.stars)}
                <span className="text-slate-400 text-xs ml-2 font-normal">Проверенный заказчик</span>
              </div>
              <p className="text-sm text-slate-700 mt-2 leading-relaxed">{r.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Portfolio Lightbox Modal */}
      {previewProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-xs p-4 animate-fadeIn">
          <div className="w-full max-w-2xl bg-white rounded-3xl overflow-hidden shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between p-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900 text-base">{previewProject.title}</h3>
              <button
                type="button"
                onClick={() => setPreviewProject(null)}
                className="p-1 rounded-full text-slate-500 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            {previewProject.photo ? (
              <PhotoView
                src={previewProject.photo}
                alt=""
                sizes="(max-width: 640px) 100vw, 42rem"
                className="h-56 w-full object-cover sm:h-80"
              />
            ) : null}
            <div className="p-5 flex items-center justify-between bg-slate-50">
              <p className="text-xs text-slate-500">Выполнено по СНиП РК с актами скрытых работ</p>
              <button
                type="button"
                onClick={() => setPreviewProject(null)}
                className="btn-ice !py-2 !px-4 text-xs font-semibold"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
