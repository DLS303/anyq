"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { orderMaterial } from "@/lib/api";
import { MATERIAL_CAT, money } from "@/lib/format";
import type { Locale, Material } from "@/lib/types";
import { PhotoView } from "@/components/media/PhotoView";
import { t } from "@/i18n/messages";
import { registerLink } from "@/lib/registration";
import { CheckCircle2, Minus, Plus, ShieldCheck, Truck, ArrowRight, User } from "lucide-react";

export function MaterialView({ locale, item }: { locale: Locale; item: Material }) {
  const m = t(locale);
  const router = useRouter();
  const { user } = useAuth();
  const [qty, setQty] = useState(Number(item.min_qty) || 1);
  const [address, setAddress] = useState("г. Алматы");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [customerName, setCustomerName] = useState(user?.full_name ?? "");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function adjustQty(delta: number) {
    setQty((prev) => Math.max(item.min_qty, prev + delta));
  }

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
        router.push(registerLink(locale) ?? `/${locale}/login`);
        return;
      }

      const o = await orderMaterial(user.email, {
        material_id: item.id,
        qty: Number(qty),
        address,
        phone,
      });

      setDone(o.id);
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("anyq-toast", {
            detail: { message: `Заказ #${o.id} на поставку ${qty} ${item.unit} успешно оформлен!` },
          })
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка оформления заказа");
    } finally {
      setBusy(false);
    }
  }

  const title = locale === "kk" ? item.title_kk : item.title_ru;
  const desc = locale === "kk" ? item.description_kk : item.description_ru;
  const amount = Number(qty || 0) * item.price_kzt;

  return (
    <div className="grid md:grid-cols-[1.15fr_0.85fr] gap-8">
      <div className="space-y-6">
        {item.photo ? (
          <PhotoView
            src={item.photo}
            alt=""
            sizes="(max-width: 640px) 100vw, 60vw"
            className="h-56 w-full rounded-3xl border border-slate-200 object-cover shadow-luxury sm:h-80"
          />
        ) : null}

        <div className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
          <div className="flex items-center gap-2 mb-2">
            <span className="pill text-[11px] text-slate-600 font-semibold">{MATERIAL_CAT[item.category][locale]}</span>
            {item.certified_rk ? (
              <span className="pill text-[11px] text-emerald-800 bg-emerald-50 border-emerald-200 font-semibold flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                {m.certifiedBadge}
              </span>
            ) : null}
          </div>

          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900 mt-2">{title}</h1>
          <p className="mt-4 text-slate-600 leading-relaxed text-sm sm:text-base">{desc}</p>

          <div className="mt-6 pt-6 border-t border-slate-100 flex flex-wrap items-baseline gap-3">
            <span className="text-3xl font-extrabold text-pine">{money(item.price_kzt, locale)}</span>
            <span className="text-sm font-medium text-slate-500">/ {item.unit} (с НДС)</span>
          </div>

          <div className="mt-3 flex items-center gap-4 text-xs font-medium text-slate-500">
            <span>Локация: {item.city}</span>
            <span>•</span>
            <span>На складе: {item.stock} {item.unit}</span>
            <span>•</span>
            <span>Мин. партия: {item.min_qty} {item.unit}</span>
          </div>
        </div>
      </div>

      {/* Order Panel Card */}
      <div className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90 h-fit">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-xl font-bold text-slate-900">{m.orderMat}</h2>
            <p className="text-xs text-slate-500 mt-0.5">Прямой договор поставки на объект</p>
          </div>
          <Truck className="h-6 w-6 text-pine" />
        </div>

        {done ? (
          <div className="mt-6 p-5 rounded-2xl bg-emerald-50 border border-emerald-200">
            <div className="flex items-center gap-2 text-emerald-900 font-bold">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              <span>Заказ #{done} оформлен</span>
            </div>
            <p className="text-xs text-emerald-800 mt-2 leading-relaxed">
              Позиция зарезервирована на складе поставщика. Сделка создана в воронке CRM.
            </p>
            <div className="mt-5 flex flex-wrap gap-2 text-xs">
              <Link
                href={`/${locale}/cabinet`}
                className="btn-ice !py-2 !px-4 text-xs font-semibold"
              >
                {m.navCabinet}
              </Link>
              <Link
                href={`/${locale}/crm`}
                className="btn-ghost !py-2 !px-4 text-xs font-semibold"
              >
                {m.navCrm}
              </Link>
            </div>
          </div>
        ) : (
          <div className="mt-6 grid gap-4">
            {/* Quantity Selector with +/- */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                {m.qty} ({item.unit}, мин. {item.min_qty})
              </label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => adjustQty(-1)}
                  className="h-11 w-11 rounded-xl bg-slate-100 border border-slate-200 grid place-items-center hover:bg-slate-200 text-slate-700 font-bold transition-colors"
                >
                  <Minus className="h-4 w-4" />
                </button>
                <input
                  type="number"
                  min={item.min_qty}
                  value={qty}
                  onChange={(e) => setQty(Math.max(item.min_qty, Number(e.target.value)))}
                  className="flex-1 text-center font-bold text-lg text-slate-900 border border-slate-200 rounded-xl px-3 py-2 bg-white"
                />
                <button
                  type="button"
                  onClick={() => adjustQty(1)}
                  className="h-11 w-11 rounded-xl bg-slate-100 border border-slate-200 grid place-items-center hover:bg-slate-200 text-slate-700 font-bold transition-colors"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Delivery Address */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                Адрес объекта доставки
              </label>
              <input
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="г. Алматы, мкр. Бесагаш, участок 14"
                className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
              />
            </div>

            {/* Customer Contact */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                  Контактное лицо
                </label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  placeholder="Имя"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                  {m.phone}
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+7 (701) 000-00-00"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                />
              </div>
            </div>

            {/* Calculation summary */}
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 my-1">
              <div className="flex justify-between items-center text-xs text-slate-500">
                <span>Объем:</span>
                <span className="font-semibold text-slate-700">{qty} {item.unit}</span>
              </div>
              <div className="flex justify-between items-center text-xs text-slate-500 mt-1">
                <span>Цена за ед.:</span>
                <span className="font-semibold text-slate-700">{money(item.price_kzt, locale)}</span>
              </div>
              <div className="flex justify-between items-baseline mt-3 pt-3 border-t border-slate-200">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-900">Итого:</span>
                <span className="text-xl font-extrabold text-pine">{money(amount, locale)}</span>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="button"
              onClick={order}
              disabled={busy}
              className="btn-ice w-full font-bold text-sm shadow-navy justify-center"
            >
              <Truck className="h-4 w-4" />
              <span>{busy ? "Оформление..." : "Заказать на объект"}</span>
            </button>

            {error ? <p className="text-xs text-red-600 font-semibold">{error}</p> : null}

            <p className="text-[11px] text-slate-400 text-center">
              Заявка на поставку. Оплата через сервис не проводится.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
