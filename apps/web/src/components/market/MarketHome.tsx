"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Anvil, Bolt, PanelsTopLeft, Search, Thermometer } from "lucide-react";
import { MarketCard } from "./MarketCard";
import { useBasket } from "./MarketShell";
import { CATEGORY_TITLES } from "@/lib/market";
import { fetchCatalog, fetchCities, fetchHome } from "@/lib/marketApi";
import { useAuth } from "@/lib/auth";
import { useDebounced } from "@/lib/useDebounced";
import { ErrorRetry, useAsync } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

const ICONS: Record<string, typeof Anvil> = {
  Металлопрокат: Anvil,
  "Сэндвич-панели": PanelsTopLeft,
  Крепёж: Bolt,
  Утеплитель: Thermometer,
};

const PRICE_CAP = 10_000_000;

export function MarketHome({ locale }: { locale: Locale }) {
  const router = useRouter();
  const params = useSearchParams();
  const category = params.get("category") ?? "";
  const { user } = useAuth();
  const basket = useBasket();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [city, setCity] = useState("");
  const [capped, setCapped] = useState(false);
  const [limit, setLimit] = useState(20);
  const debounced = useDebounced(q.trim(), 300);
  const active = Boolean(category || debounced);

  const home = useAsync((signal) => fetchHome(signal), []);
  const cities = useAsync((signal) => (active ? fetchCities(signal) : Promise.resolve([] as string[])), [active]);
  const catalog = useAsync(
    (signal) =>
      active
        ? fetchCatalog(
            { q: debounced, category, city, priceMax: capped ? PRICE_CAP : undefined, limit },
            signal,
          )
        : Promise.resolve({ items: [], total: 0 }),
    [active, debounced, category, city, capped, limit],
  );

  function openCategory(next: string) {
    const query = new URLSearchParams();
    if (next) query.set("category", next);
    if (q.trim()) query.set("q", q.trim());
    setLimit(20);
    router.push(`/${locale}/market${query.toString() ? `?${query}` : ""}`);
  }

  const tiles = home.data?.categories?.length
    ? home.data.categories
    : CATEGORY_TITLES.map((title) => ({ id: title, title }));

  return (
    <div className="grid gap-4">
      <h1 className="sr-only">Снабжение</h1>
      <label className="relative block">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
        <input
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setLimit(20);
          }}
          placeholder="Арматура, саморез, панель"
          className="min-h-14 w-full rounded-full border border-slate-200 bg-white pl-12 pr-4 text-base text-ink shadow-luxury outline-none focus:border-pine"
          enterKeyHint="search"
        />
      </label>

      {user?.role === "supplier" ? (
        <a href={`/${locale}/market/manage`} className="text-sm font-medium text-pine">
          Мой прайс
        </a>
      ) : null}

      {!active ? (
        <div className="grid grid-cols-2 gap-3">
          {tiles.map((tile) => {
            const Icon = ICONS[tile.title] ?? Anvil;
            return (
              <button
                key={tile.id}
                type="button"
                onClick={() => openCategory(tile.title)}
                className="flex min-h-36 flex-col items-start justify-between rounded-3xl bg-pine p-4 text-left text-white shadow-luxury"
              >
                <Icon className="h-7 w-7" aria-hidden />
                <span className="text-lg font-semibold leading-tight">{tile.title}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {(home.data?.categories ?? []).map((tile) => {
              const on = tile.title === category;
              return (
                <button
                  key={tile.id}
                  type="button"
                  onClick={() => openCategory(on ? "" : tile.title)}
                  className={`min-h-12 rounded-full px-4 text-sm font-medium ${on ? "bg-pine text-white" : "bg-white text-ink"}`}
                >
                  {tile.title}
                </button>
              );
            })}
            {(cities.data ?? []).map((name) => {
              const on = name === city;
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() => {
                    setCity(on ? "" : name);
                    setLimit(20);
                  }}
                  className={`min-h-12 rounded-full px-4 text-sm ${on ? "bg-pine text-white" : "bg-white text-slate-600"}`}
                >
                  {name}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => {
                setCapped((value) => !value);
                setLimit(20);
              }}
              className={`min-h-12 rounded-full px-4 text-sm ${capped ? "bg-pine text-white" : "bg-white text-slate-600"}`}
            >
              до 100 000 ₸
            </button>
          </div>

          {catalog.status === "error" ? (
            <ErrorRetry message="Не удалось загрузить каталог" retryLabel="Ещё раз" onRetry={catalog.reload} />
          ) : catalog.loading ? (
            <div className="grid gap-3" aria-busy="true">
              <div className="h-48 animate-pulse rounded-3xl bg-slate-200/80" />
              <div className="h-48 animate-pulse rounded-3xl bg-slate-200/80" />
              <div className="h-48 animate-pulse rounded-3xl bg-slate-200/80" />
            </div>
          ) : catalog.data && catalog.data.items.length === 0 ? (
            <p className="rounded-3xl bg-white px-4 py-10 text-center text-base text-slate-600">
              Ничего не нашли. Попробуйте другое название.
            </p>
          ) : (
            <div className="grid gap-3">
              {catalog.data?.items.map((item) => (
                <MarketCard
                  key={item.id}
                  locale={locale}
                  item={item}
                  inBasket={basket.has(item.id)}
                  onAdd={() => basket.add(item)}
                />
              ))}
              {catalog.data && catalog.data.items.length < catalog.data.total ? (
                <button
                  type="button"
                  className="min-h-14 rounded-full bg-white text-base font-semibold text-pine"
                  onClick={() => setLimit((value) => value + 20)}
                >
                  Ещё
                </button>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}
