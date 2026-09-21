"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import {
  createMaterial,
  fetchFavorites,
  fetchInquiries,
  fetchMaterialOrders,
  fetchMyPlots,
  fetchOrders,
  fetchSupplierMaterials,
  reviewOrder,
  setMaterialOrderStatus,
  setOrderStatus,
} from "@/lib/api";
import { MAT_ORDER, ORDER_ST, STATUS, money, titleOf } from "@/lib/format";
import type { Inquiry, Locale, Material, MaterialOrder, Plot, ServiceOrder } from "@/lib/types";
import { t } from "@/i18n/messages";

export function CabinetView({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();
  const [plots, setPlots] = useState<Plot[]>([]);
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [favorites, setFavorites] = useState<Plot[]>([]);
  const [orders, setOrders] = useState<ServiceOrder[]>([]);
  const [matOrders, setMatOrders] = useState<MaterialOrder[]>([]);
  const [skus, setSkus] = useState<Material[]>([]);
  const [error, setError] = useState("");

  function load() {
    if (!user) return;
    Promise.all([
      fetchMyPlots(user.email),
      fetchInquiries(user.email),
      fetchFavorites(user.email),
      fetchOrders(user.email),
      fetchMaterialOrders(user.email),
      user.role === "supplier" || user.role === "admin" ? fetchSupplierMaterials(user.email) : Promise.resolve([]),
    ])
      .then(([p, i, f, o, mo, sku]) => {
        setPlots(p);
        setInquiries(i);
        setFavorites(f);
        setOrders(o);
        setMatOrders(mo);
        setSkus(sku);
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (!user) {
    return (
      <p>
        <Link href={`/${locale}/login`} className="underline">
          {m.navLogin}
        </Link>
      </p>
    );
  }

  const isOwner = user.role === "owner" || user.role === "admin";

  return (
    <div className="grid gap-10">
      <p className="text-ink/55 text-sm">
        {user.full_name} · {user.email} · {user.role}
      </p>
      {error ? <p className="text-clay text-sm">{error}</p> : null}

      {isOwner ? (
        <section>
          <h2 className="font-serif text-2xl mb-3">{m.listings}</h2>
          <div className="grid gap-3">
            {plots.map((plot) => (
              <div key={plot.id} className="border border-ink/10 bg-white/50 p-4 flex justify-between gap-4">
                <div>
                  <p className="font-serif text-xl">{titleOf(plot, locale)}</p>
                  <p className="text-sm text-ink/55">
                    {STATUS[plot.status][locale]} · {plot.cadastral_no}
                    {plot.moderation_note ? ` · ${plot.moderation_note}` : ""}
                  </p>
                  {plot.status === "draft" || plot.status === "pending" || plot.status === "needs_revision" ? (
                    <Link href={`/${locale}/publish?id=${plot.id}`} className="text-sm underline mt-2 inline-block">
                      {m.edit}
                    </Link>
                  ) : null}
                </div>
                <p className="text-sm">{money(plot.price_kzt, locale)}</p>
              </div>
            ))}
            {plots.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
          </div>
        </section>
      ) : null}

      <section>
        <h2 className="font-serif text-2xl mb-3">{isOwner ? m.incoming : m.myInquiries}</h2>
        <div className="grid gap-3">
          {inquiries.map((item) => (
            <div key={item.id} className="border border-ink/10 p-4 text-sm">
              <p className="font-medium">{item.plot_title}</p>
              <p className="text-ink/60">
                {item.name} · {item.phone}
              </p>
              {item.message ? <p className="mt-1">{item.message}</p> : null}
            </div>
          ))}
          {inquiries.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
        </div>
      </section>

      <section>
        <h2 className="font-serif text-2xl mb-3">{m.myOrders}</h2>
        <div className="grid gap-3">
          {orders.map((o) => (
            <div key={o.id} className="border border-ink/10 p-4 text-sm">
              <p>
                {o.id} · {ORDER_ST[o.status]?.[locale] ?? o.status}
                {o.quote_kzt ? ` · ${money(o.quote_kzt, locale)}` : ""}
              </p>
              <p className="text-ink/55 mt-1">{o.message}</p>
              <div className="flex flex-wrap gap-3 mt-2">
                {o.thread_id ? (
                  <Link href={`/${locale}/chat/${o.thread_id}`} className="underline">
                    {m.navChat}
                  </Link>
                ) : null}
                {(user.role === "specialist" || user.role === "contractor" || user.role === "supervisor") &&
                o.status !== "completed" ? (
                  <>
                    <button type="button" className="underline" onClick={() => setOrderStatus(user.email, o.id, "quoted", 120000).then(load)}>
                      {m.quote}
                    </button>
                    <button type="button" className="underline" onClick={() => setOrderStatus(user.email, o.id, "completed").then(load)}>
                      {m.complete}
                    </button>
                  </>
                ) : null}
                {user.role === "buyer" && o.status === "completed" ? (
                  <button
                    type="button"
                    className="underline"
                    onClick={() => reviewOrder(user.email, o.id, 5, "Работа принята").then(load).catch((err: Error) => setError(err.message))}
                  >
                    {m.reviews} ★5
                  </button>
                ) : null}
              </div>
            </div>
          ))}
          {orders.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
        </div>
      </section>

      <section>
        <h2 className="font-serif text-2xl mb-3">{m.matOrders}</h2>
        <div className="grid gap-3">
          {matOrders.map((o) => (
            <div key={o.id} className="border border-ink/10 p-4 text-sm flex justify-between gap-3">
              <div>
                <p className="font-medium">
                  {o.material_title} · {o.qty} {o.unit}
                </p>
                <p className="text-ink/55">
                  {MAT_ORDER[o.status]?.[locale] ?? o.status} · {money(o.amount_kzt, locale)}
                </p>
              </div>
              {user.role === "supplier" || user.role === "admin" ? (
                <div className="flex flex-col gap-1 text-xs">
                  <button type="button" className="underline" onClick={() => setMaterialOrderStatus(user.email, o.id, "confirmed").then(load)}>
                    {m.confirm}
                  </button>
                  <button type="button" className="underline" onClick={() => setMaterialOrderStatus(user.email, o.id, "shipped").then(load)}>
                    {m.shipped}
                  </button>
                  <button type="button" className="underline" onClick={() => setMaterialOrderStatus(user.email, o.id, "delivered").then(load)}>
                    {m.delivered}
                  </button>
                </div>
              ) : null}
            </div>
          ))}
          {matOrders.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
        </div>
      </section>

      {user.role === "supplier" || user.role === "admin" ? (
        <section>
          <h2 className="font-serif text-2xl mb-3">{m.addSku}</h2>
          <form
            className="grid sm:grid-cols-2 gap-3 max-w-xl mb-4"
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
              e.currentTarget.reset();
            }}
          >
            <input name="title_ru" required placeholder="название" className="border border-ink/15 px-3 py-2" />
            <input name="price_kzt" required type="number" placeholder="₸" className="border border-ink/15 px-3 py-2" />
            <input name="unit" placeholder="т / шт / мешок" className="border border-ink/15 px-3 py-2" />
            <input name="stock" type="number" placeholder="склад" className="border border-ink/15 px-3 py-2" />
            <button className="bg-pine text-paper py-2 sm:col-span-2">{m.addSku}</button>
          </form>
          <div className="grid gap-2 text-sm">
            {skus.map((s) => (
              <p key={s.id}>
                {s.title_ru} · {money(s.price_kzt, locale)} / {s.unit}
              </p>
            ))}
          </div>
        </section>
      ) : null}

      <section>
        <h2 className="font-serif text-2xl mb-3">{m.myFavorites}</h2>
        <div className="grid gap-3">
          {favorites.map((plot) => (
            <Link key={plot.id} href={`/${locale}/plots/${plot.slug}`} className="border border-ink/10 p-4 hover:border-pine">
              {titleOf(plot, locale)} · {money(plot.price_kzt, locale)}
            </Link>
          ))}
          {favorites.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
        </div>
      </section>
    </div>
  );
}
