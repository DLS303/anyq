"use client";

import { useState } from "react";
import { fetchRequest, submitOffer } from "@/lib/marketApi";
import { ErrorRetry, useAsync } from "@/lib/useAsync";

export function MarketOffer({ requestId }: { requestId: string }) {
  const query = useAsync((signal) => fetchRequest(requestId, signal), [requestId]);
  const [source, setSource] = useState("");
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [analogs, setAnalogs] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const view = query.data;

  async function send() {
    if (!view || pending) return;
    setPending(true);
    setError("");
    try {
      await submitOffer({
        request_id: view.id,
        source: source.trim(),
        lines: view.lines.map((line) => ({
          request_line_id: line.id,
          catalog_id: line.catalog_id,
          name: line.name,
          unit: line.unit,
          qty: line.qty,
          price_tiyn: Number(prices[line.id] || 0),
          analog: Boolean(analogs[line.id]),
          source: source.trim(),
        })),
      });
      setNote("Цена отправлена");
      query.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не отправилось");
    } finally {
      setPending(false);
    }
  }

  if (query.status === "error") {
    return <ErrorRetry message="Заявка не открылась" retryLabel="Ещё раз" onRetry={query.reload} />;
  }
  if (!view) {
    return <div className="h-48 animate-pulse rounded-3xl bg-slate-200/80" aria-busy="true" />;
  }

  return (
    <div className="grid gap-4">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">Ответить на заявку</h1>
        <p className="mt-1 text-sm text-slate-600">{view.title}</p>
      </header>
      {note ? <p className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{note}</p> : null}
      {view.offers[0] ? (
        <p className="text-sm text-slate-600">Уже есть цена. Новая отправится следующей версией.</p>
      ) : null}
      <label className="grid gap-1 text-sm font-medium text-ink">
        Источник цены
        <input
          value={source}
          onChange={(event) => setSource(event.target.value)}
          className="min-h-14 rounded-2xl border border-slate-200 px-4 text-base"
          placeholder="Прайс или счёт"
        />
      </label>
      <div className="grid gap-3">
        {view.lines.map((line) => (
          <label key={line.id} className="grid gap-2 rounded-3xl bg-white p-4 shadow-luxury">
            <span className="text-sm font-medium text-ink">
              {line.name} · {line.qty} {line.unit}
            </span>
            <input
              inputMode="numeric"
              value={prices[line.id] ?? ""}
              onChange={(event) => setPrices((current) => ({ ...current, [line.id]: event.target.value }))}
              placeholder="Цена, тиын"
              className="min-h-14 rounded-2xl border border-slate-200 px-4 text-base"
            />
            <span className="flex min-h-12 items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={Boolean(analogs[line.id])}
                onChange={(event) => setAnalogs((current) => ({ ...current, [line.id]: event.target.checked }))}
              />
              аналог
            </span>
          </label>
        ))}
      </div>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <button
        type="button"
        className="inline-flex min-h-14 items-center justify-center rounded-full bg-pine text-base font-semibold text-white disabled:opacity-60"
        onClick={send}
        disabled={pending}
      >
        Отправить цену
      </button>
    </div>
  );
}
