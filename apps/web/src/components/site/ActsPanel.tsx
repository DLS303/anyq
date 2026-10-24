"use client";

import { useState } from "react";
import {
  ApiError,
  createKsAct,
  downloadKs,
  fetchKsAct,
  fetchKsActs,
  saveKsLines,
  submitKsAct,
  type KsAct,
} from "@/lib/api";
import { lastMonth } from "@/lib/ksPeriod";
import { ErrorRetry, LoadingSkeleton, useAsync } from "@/lib/useAsync";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

const field = "w-full min-h-12 border border-ink/15 bg-white px-3 text-sm";
const primary =
  "inline-flex min-h-12 w-full items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";

function statusLabel(status: string, m: ReturnType<typeof t>) {
  if (status === "draft") return m.ksStatusDraft;
  if (status === "submitted") return m.ksStatusSubmitted;
  if (status === "signed") return m.ksStatusSigned;
  if (status === "rejected") return m.ksStatusRejected;
  if (status === "cancelled") return m.ksStatusCancelled;
  return status;
}

export function ActsPanel({ locale, projectId }: { locale: Locale; projectId: string }) {
  const m = t(locale);
  const query = useAsync((signal) => fetchKsActs(projectId, signal), [projectId]);
  const [draft, setDraft] = useState<KsAct | null>(null);
  const [qty, setQty] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const period = lastMonth();

  function openDraft(act: KsAct) {
    setDraft(act);
    const next: Record<string, string> = {};
    for (const line of act.lines || []) next[line.id] = line.qty_period;
    setQty(next);
  }

  async function createAct() {
    setBusy(true);
    setFormError("");
    try {
      const act = await createKsAct(
        projectId,
        { id: crypto.randomUUID(), ...period },
        crypto.randomUUID(),
      );
      openDraft(act);
      query.reload();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : m.ksError);
    } finally {
      setBusy(false);
    }
  }

  async function persist(send: boolean) {
    if (!draft) return;
    setBusy(true);
    setFormError("");
    try {
      const saved = await saveKsLines(
        draft.id,
        {
          row_version: draft.row_version,
          lines: (draft.lines || []).map((line) => ({ id: line.id, qty_period: qty[line.id] || "0" })),
        },
        crypto.randomUUID(),
      );
      const next = send ? await submitKsAct(saved.id, saved.row_version, crypto.randomUUID()) : saved;
      openDraft(next);
      query.reload();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : m.ksError);
    } finally {
      setBusy(false);
    }
  }

  if (query.status === "loading" && !query.data) {
    return (
      <div className="grid gap-3" data-ks-panel>
        <p className="text-sm text-ink/70">{m.ksLoading}</p>
        <LoadingSkeleton label={m.ksLoading} />
      </div>
    );
  }
  if (query.status === "error") {
    return (
      <div data-ks-panel>
        <ErrorRetry message={m.ksError} retryLabel={m.retry} onRetry={query.reload} />
      </div>
    );
  }

  const acts = query.data || [];
  return (
    <div className="grid gap-3" data-ks-panel>
      <button type="button" className={primary} disabled={busy} onClick={() => void createAct()}>
        {m.ksNew}
      </button>
      {formError ? (
        <p className="text-sm" role="alert">
          {formError}
        </p>
      ) : null}
      {draft ? (
        <form
          className="grid gap-2 border border-ink/10 bg-white/70 p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void persist(true);
          }}
        >
          <p className="text-sm">
            {draft.period_from} – {draft.period_to}
          </p>
          <p className="text-sm">{statusLabel(draft.status, m)}</p>
          {(draft.lines || []).map((line) => (
            <label key={line.id} className="grid gap-1 text-sm">
              {line.name}
              <span className="text-ink/60">{m.ksQty}</span>
              <input
                className={field}
                inputMode="decimal"
                value={qty[line.id] ?? line.qty_period}
                disabled={draft.status !== "draft" || busy}
                onChange={(event) => setQty((prev) => ({ ...prev, [line.id]: event.target.value }))}
              />
              {line.over_contract ? <span className="text-ink/70">{m.ksOver}</span> : null}
            </label>
          ))}
          {draft.status === "draft" ? (
            <div className="grid gap-2">
              <button type="button" className={primary} disabled={busy} onClick={() => void persist(false)}>
                {m.ksSave}
              </button>
              <button type="submit" className={primary} disabled={busy}>
                {m.ksSend}
              </button>
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className={primary}
              onClick={() => void downloadKs(`/v1/site/ks-acts/${draft.id}/ks2.pdf`, `ks2-${draft.number}.pdf`)}
            >
              {m.ksPdf}
            </button>
            <button
              type="button"
              className={primary}
              onClick={() => void downloadKs(`/v1/site/ks-acts/${draft.id}/ks2.xlsx`, `ks2-${draft.number}.xlsx`)}
            >
              {m.ksXlsx}
            </button>
          </div>
        </form>
      ) : null}
      {acts.length === 0 && !draft ? <p className="text-sm text-ink/70">{m.ksEmpty}</p> : null}
      <ul className="grid gap-2">
        {acts.map((act) => (
          <li key={act.id}>
            <button
              type="button"
              className="grid min-h-12 w-full gap-1 border border-ink/10 bg-white/70 px-3 py-2 text-left text-sm"
              onClick={() => {
                void fetchKsAct(act.id)
                  .then(openDraft)
                  .catch((error: unknown) => setFormError(error instanceof ApiError ? error.message : m.ksError));
              }}
            >
              <span>
                {act.number} · {statusLabel(act.status, m)}
              </span>
              <span className="text-ink/60">
                {act.period_from} – {act.period_to}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
