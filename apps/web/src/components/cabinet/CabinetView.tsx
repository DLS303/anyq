"use client";

import { useState } from "react";
import { ConsentsPanel } from "@/components/cabinet/ConsentsPanel";
import { SupplierInbox } from "@/components/cabinet/SupplierInbox";
import { SupplierProfile } from "@/components/cabinet/SupplierProfile";
import { InvitePanel } from "@/components/invites/InvitePanel";
import { ProjectList } from "@/components/site/ProjectList";
import { ErrorRetry, LoadingSkeleton, useAsync, useSubmitLock } from "@/lib/useAsync";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import {
  createMaterial,
  fetchMaterialOrders,
  fetchOrders,
  fetchProcInbox,
  fetchSupplierMaterials,
  reviewOrder,
  setMaterialOrderStatus,
  setOrderStatus,
} from "@/lib/api";
import { MAT_ORDER, ORDER_ST, money } from "@/lib/format";
import type { Locale, Material, MaterialOrder, ServiceOrder } from "@/lib/types";
import { t } from "@/i18n/messages";
import { PILOT_MODE } from "@/lib/pilot";
import {
  Building2,
  CheckCircle2,
  HardHat,
  Layers,
  MessageSquare,
  Package,
  Plus,
  ShieldCheck,
  Star,
  Truck,
  User as UserIcon,
  Briefcase,
  ExternalLink,
} from "lucide-react";

function roleLabel(role: string) {
  if (role === "supplier") return "Поставщик";
  if (role === "contractor") return "Исполнитель услуг";
  if (role === "specialist") return "Подрядчик";
  if (role === "customer" || role === "buyer" || role === "owner") return "Заказчик";
  if (role === "admin") return "Администратор";
  if (role === "moderator") return "Модератор";
  return role;
}

export function CabinetView({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();
  const [error, setError] = useState("");
  const loaded = useAsync(async (signal) => {
    if (!user) return { orders: [] as ServiceOrder[], matOrders: [] as MaterialOrder[], skus: [] as Material[] };
    const [orders, matOrders, skus] = await Promise.all([
      fetchOrders(user.email, signal),
      fetchMaterialOrders(user.email, signal),
      user.role === "supplier" || user.role === "admin" ? fetchSupplierMaterials(user.email, signal) : Promise.resolve([]),
    ]);
    return { orders, matOrders, skus };
  }, [user?.email, user?.role]);
  const actions = useSubmitLock();
  const inbox = useAsync(async (signal) => {
    if (!user || user.role !== "supplier") return [];
    return fetchProcInbox(signal);
  }, [user?.id, user?.role]);
  const orders = loaded.data?.orders ?? [];
  const matOrders = loaded.data?.matOrders ?? [];
  const skus = loaded.data?.skus ?? [];
  const load = loaded.reload;
  const [addingSku, setAddingSku] = useState(false);
  const [quotes, setQuotes] = useState<Record<string, { amount: string; term: string; comment: string }>>({});
  const [reviews, setReviews] = useState<Record<string, { stars: number; text: string }>>({});
  const [reviewed, setReviewed] = useState<Record<string, boolean>>({});

  function quoteDraft(orderId: string) {
    return quotes[orderId] ?? { amount: "", term: "", comment: "" };
  }

  function reviewDraft(orderId: string) {
    return reviews[orderId] ?? { stars: 0, text: "" };
  }

  async function handleSetStatus(
    orderId: string,
    status: string,
    quote?: { amount: number; term: string; comment: string },
  ) {
    if (!user || actions.pending) return;
    await actions.run(async () => {
    try {
      await setOrderStatus(user.email, orderId, {
        status,
        quote_kzt: quote?.amount,
        quote_term: quote?.term,
        quote_comment: quote?.comment,
      });
      load();
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("anyq-toast", {
            detail: { message: `Статус заказа обновлен: ${status}` },
          })
        );
      }
    } catch (e) {
      setError((e as Error).message);
    }
    });
  }

  async function handleSetMatStatus(orderId: string, status: string) {
    if (!user || actions.pending) return;
    await actions.run(async () => {
    try {
      await setMaterialOrderStatus(user.email, orderId, status);
      load();
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("anyq-toast", {
            detail: { message: `Статус поставки #${orderId} изменен: ${status}` },
          })
        );
      }
    } catch (e) {
      setError((e as Error).message);
    }
    });
  }

  if (!user) {
    if (PILOT_MODE) {
      return (
        <div className="max-w-2xl mx-auto py-12 text-center">
          <div className="glass-strong rounded-3xl p-8 sm:p-10 shadow-luxury border border-slate-200">
            <div className="grid h-14 w-14 place-items-center rounded-2xl bg-pine text-white mx-auto mb-4 font-bold">AQ</div>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">{m.cabinetGuestTitle}</h1>
            <p className="mt-2 text-sm text-slate-500 max-w-md mx-auto">{m.cabinetGuestLead}</p>
            <div className="mt-6">
              <Link href={`/${locale}/login`} className="btn-ice font-semibold">
                {m.navLogin}
              </Link>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="max-w-2xl mx-auto py-12 text-center">
        <div className="glass-strong rounded-3xl p-8 sm:p-10 shadow-luxury border border-slate-200">
          <div className="grid h-14 w-14 place-items-center rounded-2xl bg-pine text-white mx-auto mb-4 font-bold">
            AQ
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">Кабинет пилота Engicon</h1>
          <p className="mt-2 text-sm text-slate-500 max-w-md mx-auto">
            Зарегистрируйте компанию: БИН, контакт и роль. Поставщик сразу публикует первую позицию в каталоге.
          </p>

          <div className="mt-6 flex flex-col items-center gap-3">
            <Link href={`/${locale}/login?mode=register`} className="btn-ice font-semibold">
              Регистрация компании
            </Link>
            <Link href={`/${locale}/login?mode=login`} className="text-xs text-slate-500 hover:underline">
              Уже есть доступ — войти
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-8">
      <ConsentsPanel locale={locale} />
      {/* Profile Bar with Instant Role Switching */}
      <div className="glass-strong rounded-3xl p-6 sm:p-7 shadow-luxury border border-slate-200/90">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div className="flex items-center gap-3.5">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-pine to-ice text-white font-bold text-base shadow-navy">
              {user.full_name.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-bold text-slate-900">{user.company || user.full_name}</h1>
                <span className="pill text-[10px] text-slate-700 bg-slate-50 border-slate-200 font-bold">
                  {roleLabel(user.role)}
                </span>
                {!PILOT_MODE && user.pilot === "engicon" ? (
                  <span className="pill text-[10px] text-white bg-[#2F5B8A] border-[#2F5B8A] font-bold">Пилот Engicon</span>
                ) : null}
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                {user.company ? `${user.full_name} · ` : ""}
                <span className="font-mono">{user.email}</span>
                {user.company_bin ? <span className="font-mono"> · БИН {user.company_bin}</span> : null}
                {user.city ? <span> · {user.city}</span> : null}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!PILOT_MODE || user.role === "owner" || user.role === "admin" ? (
              <Link
                href={`/${locale}/crm`}
                className="btn-ice text-xs font-semibold !py-2 !px-4 shadow-navy flex items-center gap-1.5"
              >
                <Briefcase className="h-3.5 w-3.5 text-amber-300" />
                <span>Открыть CRM</span>
              </Link>
            ) : null}
            {PILOT_MODE ? null : (
              <Link
                href={`/${locale}/chat`}
                className="btn-ghost text-xs font-semibold !py-2 !px-4 flex items-center gap-1.5"
              >
                <MessageSquare className="h-3.5 w-3.5 text-pine" />
                <span>Сообщения</span>
              </Link>
            )}
          </div>
        </div>

      </div>

      {user.role === "owner" ? (
        <Link href={`/${locale}/settings/features`} className="inline-flex min-h-12 items-center text-sm font-semibold text-pine underline">
          {m.settings}
          {" · "}
          {m.objectFeatures}
        </Link>
      ) : null}

      {user.role === "supplier" ? (
        <>
          <SupplierInbox
            items={inbox.data ?? []}
            error={inbox.error instanceof Error ? inbox.error.message : undefined}
          />
          <SupplierProfile />
        </>
      ) : null}

      {user.role === "owner" || user.role === "admin" ? <InvitePanel locale={locale} /> : null}

      {error ? <p className="text-sm font-semibold text-red-600 bg-red-50 p-3 rounded-xl border border-red-200">{error}</p> : null}
      {user.role === "supervisor" ? (
        <section className="glass-strong rounded-3xl border border-slate-200/90 p-6 shadow-luxury sm:p-8">
          <h2 className="text-xl font-bold text-slate-900">{m.myObjects}</h2>
          <p className="mt-1 mb-4 text-sm text-slate-500">{m.myObjectsLead}</p>
          <ProjectList locale={locale} />
        </section>
      ) : null}
      {loaded.loading ? <LoadingSkeleton label={m.hubLoading} /> : null}
      {loaded.status === "error" && !loaded.data ? (
        <ErrorRetry message={m.listLoadError} retryLabel={m.hubRetry} onRetry={load} />
      ) : null}

      {loaded.loading || (loaded.status === "error" && !loaded.data) ? null : (
      <>
      {/* Services / Contracting Orders */}
      <section className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-xl font-bold text-slate-900">{m.myOrders}</h2>
            <p className="text-xs text-slate-500 mt-0.5">Договоры подряда, изысканий и технического надзора</p>
          </div>
          {PILOT_MODE ? null : (
            <Link href={`/${locale}/specialists`} className="text-xs font-bold text-pine hover:underline">
              + Новый заказ услуги
            </Link>
          )}
        </div>

        <div className="grid gap-3">
          {orders.map((o) => (
            <div
              key={o.id}
              className="p-4 rounded-2xl bg-white border border-slate-200/80 shadow-2xs hover:shadow-xs transition-shadow"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-slate-900 text-sm">Заказ #{o.id}</span>
                  <span className="pill text-[10px] text-slate-600">
                    {ORDER_ST[o.status]?.[locale] ?? o.status}
                  </span>
                </div>
                {o.quote_kzt ? (
                  <span className="font-bold text-pine text-base">{money(o.quote_kzt, locale)}</span>
                ) : null}
              </div>

              <p className="text-slate-600 text-sm mt-2 leading-relaxed">{o.message}</p>
              {o.quote_term || o.quote_comment ? (
                <p className="text-xs text-slate-500 mt-1">
                  {o.quote_term ? `Срок: ${o.quote_term}` : ""}
                  {o.quote_term && o.quote_comment ? " · " : ""}
                  {o.quote_comment || ""}
                </p>
              ) : null}

              <div className="flex flex-wrap items-center gap-3 mt-4 pt-3 border-t border-slate-100 text-xs font-semibold">
                {!PILOT_MODE && o.thread_id ? (
                  <Link
                    href={`/${locale}/chat/${o.thread_id}`}
                    className="text-pine hover:underline flex items-center gap-1"
                  >
                    <MessageSquare className="h-3.5 w-3.5" />
                    <span>Перейти в диалог</span>
                  </Link>
                ) : null}

                {(user.role === "specialist" ||
                  user.role === "contractor" ||
                  user.role === "supervisor" ||
                  user.role === "admin" ||
                  user.role === "moderator") &&
                o.status === "requested" ? (
                  <form
                    className="grid w-full gap-2 sm:grid-cols-[1fr_1fr] ml-auto"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const draft = quoteDraft(o.id);
                      const amount = Number(draft.amount);
                      if (!Number.isFinite(amount) || amount <= 0) {
                        setError("Сумма КП должна быть больше нуля");
                        return;
                      }
                      handleSetStatus(o.id, "quoted", {
                        amount,
                        term: draft.term.trim(),
                        comment: draft.comment.trim(),
                      });
                    }}
                  >
                    <input
                      type="number"
                      min={1}
                      required
                      value={quoteDraft(o.id).amount}
                      onChange={(e) =>
                        setQuotes((prev) => ({ ...prev, [o.id]: { ...quoteDraft(o.id), amount: e.target.value } }))
                      }
                      placeholder="Сумма, ₸"
                      className="px-3 py-1.5 rounded-lg border border-amber-200 bg-white"
                    />
                    <input
                      type="text"
                      value={quoteDraft(o.id).term}
                      onChange={(e) =>
                        setQuotes((prev) => ({ ...prev, [o.id]: { ...quoteDraft(o.id), term: e.target.value } }))
                      }
                      placeholder="Срок"
                      className="px-3 py-1.5 rounded-lg border border-amber-200 bg-white"
                    />
                    <input
                      type="text"
                      value={quoteDraft(o.id).comment}
                      onChange={(e) =>
                        setQuotes((prev) => ({ ...prev, [o.id]: { ...quoteDraft(o.id), comment: e.target.value } }))
                      }
                      placeholder="Комментарий к КП"
                      className="px-3 py-1.5 rounded-lg border border-amber-200 bg-white sm:col-span-2"
                    />
                    <div className="flex items-center gap-2 sm:col-span-2">
                      <button
                        type="submit"
                        disabled={actions.pending}
                        className="min-h-11 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                      >
                        {m.quote}
                      </button>
                    </div>
                  </form>
                ) : null}

                {(user.role === "buyer" || user.role === "owner") && o.status === "quoted" ? (
                  <button
                    type="button"
                    onClick={() => handleSetStatus(o.id, "accepted")}
                    className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-900 border border-emerald-200 hover:bg-emerald-100"
                  >
                    Принять КП
                  </button>
                ) : null}

                {(user.role === "specialist" ||
                  user.role === "contractor" ||
                  user.role === "supervisor" ||
                  user.role === "admin" ||
                  user.role === "moderator") &&
                o.status === "accepted" ? (
                  <button
                    type="button"
                    onClick={() => handleSetStatus(o.id, "in_progress")}
                    className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-900 border border-blue-200 hover:bg-blue-100"
                  >
                    В работу
                  </button>
                ) : null}

                {(user.role === "specialist" ||
                  user.role === "contractor" ||
                  user.role === "supervisor" ||
                  user.role === "admin" ||
                  user.role === "moderator") &&
                o.status === "in_progress" ? (
                  <button
                    type="button"
                    onClick={() => handleSetStatus(o.id, "completed")}
                    className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-900 border border-emerald-200 hover:bg-emerald-100"
                  >
                    {m.complete}
                  </button>
                ) : null}

                {user.role === "buyer" && o.status === "completed" && !reviewed[o.id] ? (
                  <form
                    className="grid w-full gap-2 ml-auto"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const draft = reviewDraft(o.id);
                      if (draft.stars < 1 || draft.stars > 5) {
                        setError("Оценка от 1 до 5");
                        return;
                      }
                      if (!draft.text.trim()) {
                        setError("Напишите текст отзыва");
                        return;
                      }
                      if (actions.pending) return;
                      void actions.run(async () => reviewOrder(user.email, o.id, draft.stars, draft.text.trim())
                        .then(() => {
                          setReviewed((prev) => ({ ...prev, [o.id]: true }));
                          load();
                          if (typeof window !== "undefined") {
                            window.dispatchEvent(
                              new CustomEvent("anyq-toast", {
                                detail: { message: "Отзыв опубликован" },
                              })
                            );
                          }
                        })
                        .catch((err: Error) => setError(err.message)));
                    }}
                  >
                    <div className="flex items-center gap-1">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <button
                          key={star}
                          type="button"
                          onClick={() =>
                            setReviews((prev) => ({ ...prev, [o.id]: { ...reviewDraft(o.id), stars: star } }))
                          }
                          className="p-1"
                          aria-label={`${star} из 5`}
                        >
                          <Star
                            className={`h-4 w-4 ${
                              star <= reviewDraft(o.id).stars
                                ? "fill-amber-500 text-amber-500"
                                : "text-slate-300"
                            }`}
                          />
                        </button>
                      ))}
                    </div>
                    <textarea
                      required
                      rows={2}
                      value={reviewDraft(o.id).text}
                      onChange={(e) =>
                        setReviews((prev) => ({ ...prev, [o.id]: { ...reviewDraft(o.id), text: e.target.value } }))
                      }
                      placeholder="Текст отзыва"
                      className="px-3 py-1.5 rounded-lg border border-amber-200 bg-white font-normal"
                    />
                    <button
                      type="submit"
                      disabled={actions.pending}
                      className="min-h-11 justify-self-start rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                    >
                      Отправить отзыв
                    </button>
                  </form>
                ) : null}
              </div>
            </div>
          ))}
          {orders.length === 0 ? <p className="text-slate-400 text-sm py-4">{m.empty}</p> : null}
        </div>
      </section>

      {/* Materials Orders */}
      <section className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-xl font-bold text-slate-900">{m.matOrders}</h2>
            <p className="text-xs text-slate-500 mt-0.5">Поставки бетона, кирпича, арматуры и смесей</p>
          </div>
          {PILOT_MODE ? null : (
            <Link href={`/${locale}/materials`} className="text-xs font-bold text-pine hover:underline">
              + Каталог материалов
            </Link>
          )}
        </div>

        <div className="grid gap-3">
          {matOrders.map((o) => (
            <div
              key={o.id}
              className="p-4 rounded-2xl bg-white border border-slate-200/80 shadow-2xs flex flex-wrap items-center justify-between gap-4"
            >
              <div>
                <p className="font-bold text-slate-900 text-base">{o.material_title}</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Объем: {o.qty} {o.unit} · Сумма: <span className="font-semibold text-pine">{money(o.amount_kzt, locale)}</span>
                </p>
                <span className="pill text-[10px] text-slate-600 mt-2">
                  Статус: {MAT_ORDER[o.status]?.[locale] ?? o.status}
                </span>
              </div>

              {(user.role === "supplier" || user.role === "admin") && o.status === "requested" ? (
                <button
                  type="button"
                  onClick={() => handleSetMatStatus(o.id, "confirmed")}
                  className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-900 border border-blue-200 hover:bg-blue-100 text-xs font-semibold"
                >
                  {m.confirm}
                </button>
              ) : null}
              {(user.role === "supplier" || user.role === "admin") && o.status === "confirmed" ? (
                <button
                  type="button"
                  onClick={() => handleSetMatStatus(o.id, "shipped")}
                  className="px-3 py-1.5 rounded-lg bg-amber-50 text-amber-900 border border-amber-200 hover:bg-amber-100 text-xs font-semibold"
                >
                  {m.shipped}
                </button>
              ) : null}
              {(user.role === "supplier" || user.role === "admin") && o.status === "shipped" ? (
                <button
                  type="button"
                  onClick={() => handleSetMatStatus(o.id, "delivered")}
                  className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-900 border border-emerald-200 hover:bg-emerald-100 text-xs font-semibold"
                >
                  {m.delivered}
                </button>
              ) : null}
            </div>
          ))}
          {matOrders.length === 0 ? <p className="text-slate-400 text-sm py-4">{m.empty}</p> : null}
        </div>
      </section>

      {/* Supplier Catalog Management */}
      {(user.role === "supplier" || user.role === "admin") ? (
        <section className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-xl font-bold text-slate-900">{m.addSku}</h2>
              <p className="text-xs text-slate-500 mt-0.5">Управление складскими запасами поставщика</p>
            </div>
            <button
              type="button"
              onClick={() => setAddingSku((v) => !v)}
              className="btn-ice text-xs font-semibold !py-1.5 !px-3 shadow-navy flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span>Новая номенклатура</span>
            </button>
          </div>

          {addingSku && (
            <form
              className="grid sm:grid-cols-2 gap-3 max-w-xl mb-6 p-5 rounded-2xl bg-white border border-slate-200"
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                await createMaterial(user.email, {
                  title_ru: String(fd.get("title_ru")),
                  category: String(fd.get("category") || "inert"),
                  unit: String(fd.get("unit") || "т"),
                  price_kzt: Number(fd.get("price_kzt")),
                  min_qty: Number(fd.get("min_qty") || 1),
                  stock: Number(fd.get("stock") || 0),
                });
                load();
                setAddingSku(false);
                if (typeof window !== "undefined") {
                  window.dispatchEvent(
                    new CustomEvent("anyq-toast", {
                      detail: { message: "Позиция стройматериалов успешно добавлена в каталог!" },
                    })
                  );
                }
              }}
            >
              <input name="title_ru" required placeholder="Название (напр. Бетон М350 B25)" className="border border-slate-200 px-3 py-2 text-sm rounded-xl" />
              <input name="price_kzt" required type="number" placeholder="Цена за ед. (₸)" className="border border-slate-200 px-3 py-2 text-sm rounded-xl" />
              <input name="unit" placeholder="Ед. изм. (т / м3 / шт)" className="border border-slate-200 px-3 py-2 text-sm rounded-xl" />
              <input name="stock" type="number" placeholder="Остаток на складе" className="border border-slate-200 px-3 py-2 text-sm rounded-xl" />
              <button className="btn-ice text-xs font-bold py-2.5 sm:col-span-2 shadow-navy justify-center">
                Сохранить в каталоге
              </button>
            </form>
          )}

          <div className="grid gap-2">
            {skus.map((s) => (
              <div key={s.id} className="flex justify-between items-center p-3 rounded-xl bg-white border border-slate-100 text-sm">
                <span className="font-semibold text-slate-800">{s.title_ru}</span>
                <span className="font-bold text-pine">{money(s.price_kzt, locale)} / {s.unit}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      </>
      )}
    </div>
  );
}
