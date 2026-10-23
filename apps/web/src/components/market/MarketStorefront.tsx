"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { MarketCard } from "./MarketCard";
import { useBasket } from "./MarketShell";
import { contactSupplier, fetchSupplier } from "@/lib/marketApi";
import { formatTiyn } from "@/lib/market";
import { useAuth } from "@/lib/auth";
import { ErrorRetry, useAsync } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

export function MarketStorefront({ locale, companyId }: { locale: Locale; companyId: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const basket = useBasket();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const query = useAsync((signal) => fetchSupplier(companyId, signal), [companyId]);
  const shop = query.data;

  async function ask() {
    if (!user) {
      router.push(`/${locale}/login`);
      return;
    }
    if (pending) return;
    setPending(true);
    setError("");
    try {
      const created = await contactSupplier(companyId);
      router.push(`/${locale}/market/request/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не отправилось");
      setPending(false);
    }
  }

  if (query.status === "error") {
    return <ErrorRetry message="Витрина не открылась" retryLabel="Ещё раз" onRetry={query.reload} />;
  }
  if (!shop) {
    return (
      <div className="grid gap-3" aria-busy="true">
        <div className="h-40 animate-pulse rounded-3xl bg-slate-200/80" />
        <div className="h-48 animate-pulse rounded-3xl bg-slate-200/80" />
      </div>
    );
  }

  const score = shop.label || `${shop.rating.toFixed(1).replace(".", ",")} · ${shop.deal_count}`;

  return (
    <div className="grid gap-4">
      <section className="rounded-3xl bg-white p-5 shadow-luxury">
        <p className="text-sm text-slate-500">{shop.city}</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink">{shop.name}</h1>
        <p className="mt-2 text-sm text-slate-600">
          {score}
          {shop.badge ? <span className="ml-2 font-semibold text-emerald-800">{shop.badge}</span> : null}
        </p>
        <p className="mt-2 text-sm text-slate-600">
          {shop.vat_label}
          <span className="mx-1.5 text-slate-300">·</span>
          {shop.esf_label}
          <span className="mx-1.5 text-slate-300">·</span>
          {shop.verification_label}
        </p>
        <p className="mt-3 text-sm text-ink">
          {shop.delivery ? "Доставка" : "Самовывоз"}
          {shop.delivery_cities.length ? `: ${shop.delivery_cities.join(", ")}` : ""}
        </p>
        {shop.min_order_tiyn > 0 ? (
          <p className="mt-1 text-sm text-slate-500">Минимальный заказ {formatTiyn(shop.min_order_tiyn)}</p>
        ) : null}
        <button
          type="button"
          className="mt-4 inline-flex min-h-14 w-full items-center justify-center rounded-full bg-pine text-base font-semibold text-white shadow-luxury disabled:opacity-60"
          onClick={ask}
          disabled={pending}
        >
          Запросить цену
        </button>
        {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
      </section>

      <div className="grid gap-3">
        {shop.items.map((item) => (
          <MarketCard
            key={item.id}
            locale={locale}
            item={item}
            inBasket={basket.has(item.id)}
            onAdd={() => basket.add(item)}
          />
        ))}
      </div>

      {shop.reviews.length ? (
        <section className="grid gap-3">
          <h2 className="text-lg font-semibold text-ink">Отзывы</h2>
          {shop.reviews.map((review) => (
            <article key={review.id} className="rounded-3xl bg-white p-4 shadow-luxury">
              <p className="text-sm text-slate-600">
                качество {review.quality} · срок {review.delivery} · цена {review.price} · связь {review.communication}
              </p>
              {review.comment ? <p className="mt-2 text-sm text-ink">{review.comment}</p> : null}
              {review.supplier_reply ? (
                <p className="mt-2 text-sm text-slate-600">Ответ: {review.supplier_reply}</p>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}
    </div>
  );
}
