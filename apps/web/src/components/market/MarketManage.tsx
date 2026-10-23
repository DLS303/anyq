"use client";

import { useState } from "react";
import Link from "next/link";
import { fetchAssigned, fetchOwnItems, fetchOwnRating, hideOwnItem, importPrices, saveOwnItem } from "@/lib/marketApi";
import { CATEGORY_TITLES, formatTiyn, displayPriceTiyn } from "@/lib/market";
import { ErrorRetry, useAsync } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

const UNITS = ["м", "м²", "т", "шт", "уп"];

const empty = {
  name: "",
  category: CATEGORY_TITLES[0] as string,
  unit: "шт",
  price_tiyn: "",
  source: "",
  city: "",
  stock: "in_stock",
  lead_days: "0",
};

export function MarketManage({ locale }: { locale: Locale }) {
  const items = useAsync((signal) => fetchOwnItems(signal), []);
  const rating = useAsync((signal) => fetchOwnRating(signal), []);
  const assigned = useAsync((signal) => fetchAssigned(signal), []);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  function field<K extends keyof typeof empty>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      await saveOwnItem(
        {
          name: form.name,
          category: form.category,
          unit: form.unit,
          price_tiyn: Number(form.price_tiyn),
          source: form.source,
          city: form.city,
          stock: form.stock,
          lead_days: Number(form.lead_days || 0),
        },
        editing ?? undefined,
      );
      setForm(empty);
      setEditing(null);
      setNote(editing ? "Позиция обновлена" : "Позиция добавлена");
      items.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не сохранилось");
    } finally {
      setPending(false);
    }
  }

  async function toggle(id: string, hidden: boolean) {
    setError("");
    try {
      await hideOwnItem(id, hidden);
      items.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не изменилось");
    }
  }

  async function upload(file: File | undefined) {
    if (!file || pending) return;
    setPending(true);
    setError("");
    try {
      const result = await importPrices(file);
      setNote(`Загружено строк: ${result.saved}`);
      items.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Файл не принят");
    } finally {
      setPending(false);
    }
  }

  const score = rating.data;

  return (
    <div className="grid gap-4">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">Мой прайс</h1>
        {score ? (
          <p className="mt-2 text-sm text-slate-600">
            {score.name}: {score.label || `${score.rating.toFixed(1).replace(".", ",")} · ${score.deal_count}`}
            {score.badge ? ` · ${score.badge}` : ""}
          </p>
        ) : null}
        {score?.tips?.[0] ? <p className="mt-2 rounded-2xl bg-white px-4 py-3 text-sm text-ink">{score.tips[0]}</p> : null}
      </header>

      <section className="grid gap-3 rounded-3xl bg-white p-4 shadow-luxury">
        <h2 className="text-base font-semibold text-ink">{editing ? "Править позицию" : "Добавить позицию"}</h2>
        <input
          value={form.name}
          onChange={(event) => field("name", event.target.value)}
          placeholder="Название"
          className="min-h-14 rounded-2xl border border-slate-200 px-4"
        />
        <div className="grid grid-cols-2 gap-2">
          <select
            value={form.category}
            onChange={(event) => field("category", event.target.value)}
            className="min-h-14 rounded-2xl border border-slate-200 px-3"
          >
            {CATEGORY_TITLES.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
          <select
            value={form.unit}
            onChange={(event) => field("unit", event.target.value)}
            className="min-h-14 rounded-2xl border border-slate-200 px-3"
          >
            {UNITS.map((unit) => (
              <option key={unit}>{unit}</option>
            ))}
          </select>
        </div>
        <input
          inputMode="numeric"
          value={form.price_tiyn}
          onChange={(event) => field("price_tiyn", event.target.value)}
          placeholder="Цена, тиын"
          className="min-h-14 rounded-2xl border border-slate-200 px-4"
        />
        <input
          value={form.source}
          onChange={(event) => field("source", event.target.value)}
          placeholder="Источник цены"
          className="min-h-14 rounded-2xl border border-slate-200 px-4"
        />
        <div className="grid grid-cols-2 gap-2">
          <input
            value={form.city}
            onChange={(event) => field("city", event.target.value)}
            placeholder="Город"
            className="min-h-14 rounded-2xl border border-slate-200 px-4"
          />
          <input
            inputMode="numeric"
            value={form.lead_days}
            onChange={(event) => field("lead_days", event.target.value)}
            placeholder="Дней"
            className="min-h-14 rounded-2xl border border-slate-200 px-4"
          />
        </div>
        <button
          type="button"
          className="inline-flex min-h-14 items-center justify-center rounded-full bg-pine text-base font-semibold text-white disabled:opacity-60"
          onClick={save}
          disabled={pending}
        >
          {editing ? "Сохранить" : "Добавить"}
        </button>
        <label className="inline-flex min-h-14 cursor-pointer items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-ink">
          Загрузить прайс
          <input
            type="file"
            accept=".csv,.xlsx,text/csv"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              void upload(file);
            }}
          />
        </label>
      </section>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {note ? <p className="text-sm text-emerald-800">{note}</p> : null}

      {items.status === "error" ? (
        <ErrorRetry message="Прайс не загрузился" retryLabel="Ещё раз" onRetry={items.reload} />
      ) : items.loading ? (
        <div className="h-32 animate-pulse rounded-3xl bg-slate-200/80" aria-busy="true" />
      ) : (
        <div className="grid gap-3">
          {(items.data ?? []).map((item) => (
            <article key={item.id} className={`rounded-3xl bg-white p-4 shadow-luxury ${item.hidden ? "opacity-60" : ""}`}>
              <h3 className="font-semibold text-ink">{item.name}</h3>
              <p className="mt-1 text-2xl font-bold text-pine">
                {formatTiyn(displayPriceTiyn(item.price_tiyn, item.vat_included, item.vat_rate))}
              </p>
              <p className="text-sm text-slate-600">
                {item.unit} · {item.vat_label} · {item.city}
                {item.hidden ? " · скрыто" : ""}
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  className="min-h-12 flex-1 rounded-full bg-slate-100 text-sm font-semibold"
                  onClick={() => {
                    setEditing(item.id);
                    setForm({
                      name: item.name,
                      category: item.category,
                      unit: item.unit,
                      price_tiyn: String(item.price_tiyn),
                      source: item.source ?? "",
                      city: item.city,
                      stock: item.stock,
                      lead_days: String(item.lead_days),
                    });
                  }}
                >
                  Править
                </button>
                <button
                  type="button"
                  className="min-h-12 flex-1 rounded-full bg-slate-100 text-sm font-semibold"
                  onClick={() => toggle(item.id, !item.hidden)}
                >
                  {item.hidden ? "Вернуть" : "Скрыть"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {/* The supplier request list stays here until registration owns that screen. */}
      <section className="grid gap-2">
        <h2 className="text-lg font-semibold text-ink">Заявки</h2>
        {(assigned.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Новых заявок нет.</p>
        ) : (
          assigned.data?.map((row) => (
            <Link
              key={row.id}
              href={`/${locale}/market/request/${row.id}/price`}
              className="flex min-h-14 items-center rounded-2xl bg-white px-4 text-sm font-medium text-ink shadow-luxury"
            >
              {row.title}
            </Link>
          ))
        )}
      </section>
    </div>
  );
}
