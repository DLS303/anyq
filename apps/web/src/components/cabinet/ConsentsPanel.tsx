"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useMessages } from "@/lib/i18n";
import { fetchConsentDocuments, fetchConsents, grantAiConsent, grantCrossBorderConsent, revokeConsent, type ConsentRow } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

function when(iso: string | null | undefined, locale: Locale) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale === "kk" ? "kk-KZ" : "ru-KZ", {
    timeZone: "Asia/Almaty",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function labelOf(type: string, m: ReturnType<typeof useMessages>) {
  if (type === "offer_pd") return m.consentPd;
  if (type === "ai") return m.consentAi;
  if (type === "cross_border") return m.consentCross;
  if (type === "privacy") return m.consentPrivacy;
  return type;
}

export function ConsentsPanel({ locale }: { locale: Locale }) {
  const m = useMessages();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [provider, setProvider] = useState("");
  const [country, setCountry] = useState("");
  const loaded = useAsync(async (signal) => {
    const [rows, documents] = await Promise.all([fetchConsents(signal), fetchConsentDocuments(signal)]);
    return { rows, documents };
  }, [locale]);
  const rows = loaded.data?.rows ?? [];
  const documents = loaded.data?.documents ?? [];

  function latestOf(type: string) {
    const same = rows.filter((row) => row.type === type);
    return same[same.length - 1];
  }

  function canRevoke(row: ConsentRow) {
    if (row.action === "revoke") return false;
    const latest = latestOf(row.type);
    return latest?.id === row.id && latest.action !== "revoke";
  }

  async function grant() {
    setBusy(true);
    setError("");
    try {
      await grantAiConsent();
      await loaded.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(row: ConsentRow) {
    if (row.type === "offer_pd" && !window.confirm(m.consentRevokePd)) return;
    setBusy(true);
    setError("");
    try {
      await revokeConsent(row.id);
      await loaded.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  const aiOn = latestOf("ai")?.action === "grant";
  const crossOn = latestOf("cross_border")?.action === "grant";

  async function grantCross(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await grantCrossBorderConsent(provider.trim(), country.trim());
      setProvider("");
      setCountry("");
      await loaded.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="glass-strong rounded-3xl p-6 sm:p-7 shadow-luxury border border-slate-200/90">
      <h2 className="text-lg font-semibold text-slate-900">{m.consentsTitle}</h2>
      <p className="mt-1 text-sm text-slate-500">{m.consentAiHint}</p>
      {documents.length ? (
        <ul className="mt-3 grid gap-1 text-xs text-slate-500">
          {documents.map((doc) => (
            <li key={doc.key}>
              {labelOf(doc.key, m)} · {m.consentVersion} {doc.version}
            </li>
          ))}
        </ul>
      ) : null}
      {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      <div className="mt-4 grid gap-2">
        {rows.length === 0 ? <p className="text-sm text-slate-500">{m.consentEmpty}</p> : null}
        {rows.map((row) => {
          const revoked = row.action === "revoke";
          const stamp = revoked ? row.revoked_at || row.granted_at : row.granted_at;
          return (
            <article key={row.id} className="flex flex-wrap items-center justify-between gap-3 border border-slate-200 rounded-2xl px-3 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900">{labelOf(row.type, m)}</p>
                <p className="text-xs text-slate-500">
                  {revoked ? m.consentRevoked : m.consentGranted} · {when(stamp, locale)} · {m.consentVersion} {row.text_version}
                </p>
              </div>
              {canRevoke(row) ? (
                <button
                  type="button"
                  className="inline-flex min-h-12 items-center justify-center rounded-full border border-slate-300 px-4 text-sm"
                  disabled={busy}
                  onClick={() => void revoke(row)}
                >
                  {m.consentRevoke}
                </button>
              ) : null}
            </article>
          );
        })}
      </div>
      {crossOn ? null : (
        <form className="mt-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => void grantCross(event)}>
          <input
            className="min-h-12 rounded-xl border border-slate-200 px-3 text-sm"
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
            placeholder={m.consentProvider}
            aria-label={m.consentProvider}
            required
          />
          <input
            className="min-h-12 rounded-xl border border-slate-200 px-3 text-sm"
            value={country}
            onChange={(event) => setCountry(event.target.value)}
            placeholder={m.consentCountry}
            aria-label={m.consentCountry}
            required
          />
          <button
            type="submit"
            className="inline-flex min-h-12 items-center justify-center rounded-full border border-slate-300 px-4 text-sm"
            disabled={busy}
          >
            {m.consentCrossAllow}
          </button>
        </form>
      )}
      {aiOn ? null : (
        <div className="mt-4">
          <button
            type="button"
            className="inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50"
            disabled={busy}
            onClick={() => void grant()}
          >
            {m.consentAiAllow}
          </button>
          <p className="mt-2 text-xs">
            <Link href={`/${locale}/legal/ai-consent`} className="underline text-pine">
              {m.consentAiDoc}
            </Link>
          </p>
        </div>
      )}
    </section>
  );
}
