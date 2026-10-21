"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { fetchRequest, repeatRequest, selectOffer } from "@/lib/marketApi";
import { formatTiyn } from "@/lib/market";
import { ErrorRetry, useAsync } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

export function MarketCompare({ locale, requestId }: { locale: Locale; requestId: string }) {
  const router = useRouter();
  const query = useAsync((signal) => fetchRequest(requestId, signal), [requestId]);
  const [pending, setPending] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const view = query.data;

  async function choose(offerId: string) {
    if (pending) return;
    setPending(offerId);
    setError("");
    try {
      await selectOffer(offerId);
      setNote("Предложение выбрано");
      query.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не выбрано");
    } finally {
      setPending("");
    }
  }

  async function again() {
    if (pending) return;
    setPending("repeat");
    setError("");
    try {
      const created = await repeatRequest(requestId);
      router.push(`/${locale}/market/request/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не повторилось");
      setPending("");
    }
  }

  if (query.status === "error") {
    return <ErrorRetry message="Заявка не открылась" retryLabel="Ещё раз" onRetry={query.reload} />;
  }
  if (!view) {
    return (
      <div className="grid gap-3" aria-busy="true">
        <div className="h-36 animate-pulse rounded-3xl bg-slate-200/80" />
        <div className="h-36 animate-pulse rounded-3xl bg-slate-200/80" />
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">{view.title}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {view.lines.map((line) => `${line.name} · ${line.qty} ${line.unit}`).join("; ")}
        </p>
      </header>
      {note ? <p className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">{note}</p> : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {view.offers.length === 0 ? (
        <p className="rounded-3xl bg-white px-4 py-10 text-center text-base text-slate-600">
          Поставщики ещё не ответили.
        </p>
      ) : (
        <ol className="grid gap-3">
          {view.offers.map((offer) => (
            <li
              key={offer.id}
              className={`rounded-3xl border p-4 shadow-luxury ${
                offer.best ? "border-emerald-500 bg-emerald-50" : "border-slate-200 bg-white"
              }`}
            >
              <p className="text-sm font-medium text-ink">{offer.supplier_name}</p>
              <p className={`mt-2 text-3xl font-bold tracking-tight ${offer.best ? "text-emerald-700" : "text-pine"}`}>
                {formatTiyn(offer.comparable_tiyn)}
              </p>
              <p className="mt-1 text-sm text-slate-600">{offer.vat_label}</p>
              {offer.best ? <p className="mt-2 text-sm font-semibold text-emerald-700">лучшая цена</p> : null}
              {offer.suspicious ? <p className="mt-1 text-sm font-medium text-amber-800">подозрительная цена</p> : null}
              {offer.manual_review ? <p className="mt-1 text-sm text-slate-600">мало данных</p> : null}
              {offer.stale_label ? <p className="mt-1 text-sm text-amber-800">{offer.stale_label}</p> : null}
              {offer.analog_label ? <p className="mt-1 text-sm text-slate-700">{offer.analog_label}</p> : null}
              {offer.esf_label ? <p className="mt-1 text-sm text-slate-500">{offer.esf_label}</p> : null}
              <ul className="mt-3 grid gap-1 text-sm text-slate-700">
                {offer.lines.map((line) => (
                  <li key={line.id} className="break-words">
                    {line.name} · {line.qty} {line.unit} · {formatTiyn(line.comparable_tiyn)}
                    {line.analog_label ? ` · ${line.analog_label}` : ""}
                    {line.stale_label ? ` · ${line.stale_label}` : ""}
                    {line.suspicious ? " · подозрительная цена" : ""}
                    {line.manual_review ? ` · ${line.median_label}` : ""}
                  </li>
                ))}
              </ul>
              {offer.status === "selected" ? (
                <p className="mt-4 text-sm font-semibold text-emerald-800">Выбрано</p>
              ) : (
                <button
                  type="button"
                  className="mt-4 inline-flex min-h-14 w-full items-center justify-center rounded-full bg-pine text-base font-semibold text-white disabled:opacity-60"
                  onClick={() => choose(offer.id)}
                  disabled={Boolean(pending)}
                >
                  Выбрать предложение
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
      <button type="button" className="min-h-12 text-sm font-medium text-pine" onClick={again} disabled={Boolean(pending)}>
        Повторить заявку
      </button>
    </div>
  );
}
