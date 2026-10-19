"use client";

import { useEffect, useRef, useState } from "react";
import {
  createProcOffer,
  createProcRequest,
  deleteProcOffer,
  downloadProc,
  fetchProcPicker,
  fetchProcRequests,
  fetchProcSheet,
  fetchProjects,
  importProcLines,
  importProcOffers,
  openProcFile,
  patchProcLine,
  quickProcRequest,
  repeatProcRequest,
  selectProcBest,
  setProcDocumentActual,
  uploadProcDocument,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ErrorRetry, LoadingSkeleton, useAsync, useGuardedSubmit } from "@/lib/useAsync";
import { toast } from "@/lib/toast";
import { t } from "@/i18n/messages";
import type { Locale, ProcImportResult, ProcOfferCell, ProcSheet, ProcSheetLine } from "@/lib/types";

const field = "w-full min-h-12 border border-ink/15 bg-white px-3 text-sm";
const primary =
  "inline-flex min-h-12 w-full items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";
const ghost =
  "inline-flex min-h-12 w-full items-center justify-center rounded-full border border-ink/15 bg-white px-4 text-sm disabled:opacity-50";

type Copy = ReturnType<typeof t>;
type Picked = { title: string; unit: string };
type DraftLine = { id: string; title: string; unit: string; qty: string };
type Screen =
  | { kind: "ask"; step: 1 | 2 | 3 }
  | { kind: "edit"; title: string; lines: DraftLine[] }
  | { kind: "prices"; requestId: string };

function fill(template: string, values: Record<string, string | number>) {
  return Object.entries(values).reduce((text, [key, value]) => text.split(`{${key}}`).join(String(value)), template);
}

function tenge(value: number, locale: Locale) {
  const formatted = new Intl.NumberFormat(locale === "kk" ? "kk-KZ" : "ru-KZ", {
    maximumFractionDigits: 2,
  }).format(value);
  return `${formatted} ₸`;
}

function parseQty(value: string) {
  const amount = Number(value.trim().replace(",", "."));
  return Number.isFinite(amount) && amount > 0 ? amount : null;
}

function issueText(code: string, m: Copy) {
  switch (code) {
    case "name_required":
      return m.procErrName;
    case "unit_required":
      return m.procErrUnit;
    case "qty_invalid":
    case "qty_positive":
      return m.procErrQty;
    case "price_invalid":
      return m.procErrPrice;
    case "supplier_required":
      return m.procErrSupplier;
    case "pos_missing":
      return m.procErrPos;
    case "pos_required":
      return m.procErrPosRequired;
    case "phone_removed":
      return m.procErrPhone;
    default:
      return code;
  }
}

function statusText(code: ProcSheetLine["status_code"], m: Copy) {
  switch (code) {
    case "no_price":
      return m.procNoOffers;
    case "one_offer":
      return m.procOneOffer;
    case "no_compare":
      return m.procNoCompare;
    default:
      return m.procCompared;
  }
}

function requestStatus(status: string, m: Copy) {
  if (status === "decided") return m.procStatusDecided;
  if (status === "collecting") return m.procStatusCollecting;
  return m.procStatusDraft;
}

function vatText(value: boolean | null, m: Copy) {
  if (value === true) return m.procVatYes;
  if (value === false) return m.procVatNo;
  return m.procVatUnknown;
}

function StatementImport({
  m,
  resolveId,
  onSaved,
}: {
  m: Copy;
  resolveId: () => Promise<string>;
  onSaved: () => void;
}) {
  const [preview, setPreview] = useState<ProcImportResult | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const idRef = useRef<string | null>(null);

  async function ensure() {
    if (idRef.current) return idRef.current;
    const id = await resolveId();
    idRef.current = id;
    return id;
  }

  async function run(task: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    try {
      await task();
    } catch (err) {
      toast(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-3">
      <label className="grid gap-1 text-sm">
        {m.procUploadStatement}
        <input
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="block w-full text-sm"
          onChange={(event) => {
            const next = event.target.files?.[0];
            event.target.value = "";
            if (!next) return;
            void run(async () => {
              const id = await ensure();
              const result = await importProcLines(id, next, true, crypto.randomUUID());
              setPreview(result);
              setFile(next);
            });
          }}
        />
      </label>
      {preview ? (
        <div className="grid gap-2">
          <p className="text-sm text-ink/60">{m.procPreviewHint}</p>
          {preview.contact_ignored ? <p className="text-sm text-ink/60">{m.procContactIgnored}</p> : null}
          {preview.rows.map((row) => (
            <p key={row.row} className={`break-words text-sm ${row.errors.length ? "text-red-800" : "text-ink/80"}`}>
              {row.title || "—"} · {row.qty ?? "—"} {row.unit || ""}
              {row.errors.length ? ` — ${row.errors.map((code) => issueText(code, m)).join(". ")}` : ""}
            </p>
          ))}
          <button
            type="button"
            className={ghost}
            disabled={busy || !file || !preview.rows.some((row) => row.errors.length === 0)}
            onClick={() =>
              void run(async () => {
                if (!file) return;
                const id = await ensure();
                const saved = await importProcLines(id, file, false, crypto.randomUUID());
                toast(m.procImportSaved);
                if (saved.created + saved.updated > 0) {
                  setPreview(null);
                  setFile(null);
                  onSaved();
                } else {
                  setPreview(saved);
                }
              })
            }
          >
            {m.procSaveStatement}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function ProcurementTab({
  locale,
  projectId,
  projectTitle,
}: {
  locale: Locale;
  projectId: string;
  projectTitle: string;
}) {
  const m = t(locale);
  const { user } = useAuth();
  const [screen, setScreen] = useState<Screen>({ kind: "ask", step: 1 });
  const [query, setQuery] = useState("");
  const [needle, setNeedle] = useState("");
  const [picked, setPicked] = useState<Picked | null>(null);
  const [qty, setQty] = useState("");
  const [lineId, setLineId] = useState("");
  const [supplier, setSupplier] = useState("");
  const [price, setPrice] = useState("");
  const [vat, setVat] = useState<"yes" | "no" | "unknown">("yes");
  const [delivery, setDelivery] = useState("");
  const [comment, setComment] = useState("");
  const [confirmed, setConfirmed] = useState(true);
  const [fileSupplier, setFileSupplier] = useState("");
  const [invoiceSupplier, setInvoiceSupplier] = useState("");
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [invoiceAmount, setInvoiceAmount] = useState("");
  const [duplicate, setDuplicate] = useState(false);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const listQuery = useAsync(() => fetchProcRequests(projectId), [projectId]);
  const priceId = screen.kind === "prices" ? screen.requestId : null;
  const sheetQuery = useAsync(() => (priceId ? fetchProcSheet(priceId) : Promise.resolve(null)), [priceId]);
  const pickerQuery = useAsync(() => fetchProcPicker(projectId, needle), [projectId, needle]);
  const projectsQuery = useAsync(async () => {
    const rows = await fetchProjects();
    return rows.flatMap((row) => {
      const project = (row as { project?: { id?: string; title?: string } }).project;
      if (!project?.id) return [];
      return [{ id: project.id, title: project.title || project.id }];
    });
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setNeedle(query.trim()), 200);
    return () => window.clearTimeout(timer);
  }, [query]);

  const reload = () => {
    listQuery.reload();
    sheetQuery.reload();
    pickerQuery.reload();
  };
  const sendForm = useGuardedSubmit(m.procSent, m.hubSaveError, reload);
  const repeatForm = useGuardedSubmit(m.procRepeated, m.hubSaveError, reload);
  const saveForm = useGuardedSubmit(m.procSaveQty, m.hubSaveError, reload);
  const offerForm = useGuardedSubmit(m.procSavedOffer, m.hubSaveError, reload);
  const winnerForm = useGuardedSubmit(m.procSelected, m.hubSaveError, () => sheetQuery.reload());
  const sheet = sheetQuery.data;

  useEffect(() => {
    if (sheet?.lines[0] && !sheet.lines.some((line) => line.id === lineId)) setLineId(sheet.lines[0].id);
  }, [lineId, sheet]);

  if (!user) return <p className="text-sm text-ink/70">{m.needLogin}</p>;
  if (listQuery.loading || !listQuery.data) {
    if (listQuery.status === "error") {
      return <ErrorRetry message={m.hubLoadError} retryLabel={m.hubRetry} onRetry={listQuery.reload} />;
    }
    return <LoadingSkeleton label={m.hubLoading} />;
  }

  const access = sheet?.access || listQuery.data.access;
  const recent = pickerQuery.data?.recent || [];
  const catalog = pickerQuery.data?.catalog || [];
  const named = query.trim();
  const known = [...recent, ...catalog].some((item) => item.title.toLocaleLowerCase() === named.toLocaleLowerCase());
  const objects = [
    { id: projectId, title: projectTitle || projectId },
    ...(projectsQuery.data || []).filter((item) => item.id !== projectId),
  ];
  const requests = [...listQuery.data.requests].reverse();

  function chooseMaterial(item: { title: string; unit: string; qty?: number }) {
    setPicked({ title: item.title, unit: item.unit || "шт" });
    setQty(item.qty != null ? String(item.qty) : "");
    setScreen({ kind: "ask", step: 2 });
  }

  function sendTo(targetId: string) {
    if (!picked) return;
    const amount = parseQty(qty);
    const unit = picked.unit.trim();
    if (amount == null || !unit) {
      toast(m.procErrQty);
      return;
    }
    const title = picked.title;
    void sendForm.submit(async (key) => {
      await quickProcRequest(targetId, { title, unit, qty: amount }, key);
      setPicked(null);
      setQty("");
      setQuery("");
      setScreen({ kind: "ask", step: 1 });
    });
  }

  async function run(task: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    try {
      await task();
    } catch (err) {
      toast(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  function priceCell(offer: ProcOfferCell | null, lineQty: number) {
    if (!offer) return <span className="text-ink/40">—</span>;
    return (
      <span className="block">
        <span className={offer.is_best ? "font-semibold" : ""}>{tenge(offer.price_kzt, locale)}</span>
        <span className="mt-1 block text-xs text-ink/60">
          {vatText(offer.vat_included, m)}
          {offer.is_best ? ` · ${m.procBest}` : ""}
          {offer.is_selected ? " · ✓" : ""}
        </span>
        {offer.short && offer.qty_available != null ? (
          <span className="mt-1 block text-xs text-ink/60">{fill(m.procShort, { n: offer.qty_available, m: lineQty })}</span>
        ) : null}
      </span>
    );
  }

  let stepLabel = "";
  if (screen.kind === "ask" && screen.step === 1) stepLabel = m.procSearch;
  if (screen.kind === "ask" && screen.step === 2) stepLabel = m.procQty;
  if (screen.kind === "ask" && screen.step === 3) stepLabel = m.procObject;

  return (
    <div className="grid min-w-0 gap-4" data-proc={screen.kind}>
      {screen.kind === "ask" && access.can_request ? (
        <section className="grid gap-3">
          <p className="text-sm text-ink/60">
            {screen.step}/3 · {stepLabel}
          </p>
          {screen.step === 1 ? (
            <div className="grid gap-3">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={m.procSearch}
                className={field}
                aria-label={m.procSearch}
              />
              {named && !known ? (
                <button type="button" className={ghost} onClick={() => chooseMaterial({ title: named, unit: "шт" })}>
                  {fill(m.procUseName, { name: named })}
                </button>
              ) : null}
              {recent.length ? (
                <div className="grid gap-2">
                  <h2 className="text-sm font-medium">{m.procRecent}</h2>
                  {recent.map((item) => (
                    <button
                      key={`recent-${item.title}`}
                      type="button"
                      className={`${ghost} justify-between text-left`}
                      onClick={() => chooseMaterial(item)}
                    >
                      <span className="min-w-0 break-words">{item.title}</span>
                      <span className="shrink-0 text-ink/50">
                        {item.qty != null ? `${item.qty} ` : ""}
                        {item.unit}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
              {catalog.length ? (
                <div className="grid gap-2">
                  <h2 className="text-sm font-medium">{m.procCatalog}</h2>
                  {catalog.map((item) => (
                    <button
                      key={item.id || item.title}
                      type="button"
                      className={`${ghost} justify-between text-left`}
                      onClick={() => chooseMaterial(item)}
                    >
                      <span className="min-w-0 break-words">{item.title}</span>
                      <span className="shrink-0 text-ink/50">{item.unit}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {screen.step === 2 && picked ? (
            <div className="grid gap-3">
              <button type="button" className="w-fit text-sm underline" onClick={() => setScreen({ kind: "ask", step: 1 })}>
                {m.procPrev}
              </button>
              <h2 className="break-words text-xl font-medium">{picked.title}</h2>
              <label className="grid gap-1 text-sm">
                {m.procQtyStep}
                <input
                  value={qty}
                  onChange={(event) => setQty(event.target.value)}
                  inputMode="decimal"
                  className={field}
                  aria-label={m.procQty}
                />
              </label>
              <p className="text-sm text-ink/60">{picked.unit}</p>
              <details className="text-sm">
                <summary className="cursor-pointer py-2">{m.procMore}</summary>
                <label className="mt-2 grid gap-1">
                  {m.procUnit}
                  <input
                    value={picked.unit}
                    onChange={(event) => setPicked({ ...picked, unit: event.target.value })}
                    className={field}
                  />
                </label>
              </details>
              <button
                type="button"
                className={primary}
                disabled={parseQty(qty) == null || !picked.unit.trim()}
                onClick={() => setScreen({ kind: "ask", step: 3 })}
              >
                {m.procNext}
              </button>
            </div>
          ) : null}
          {screen.step === 3 && picked ? (
            <div className="grid gap-3">
              <button type="button" className="w-fit text-sm underline" onClick={() => setScreen({ kind: "ask", step: 2 })}>
                {m.procPrev}
              </button>
              <h2 className="text-xl font-medium">{m.procObject}</h2>
              <p className="text-sm text-ink/60">
                {picked.title} · {qty} {picked.unit}
              </p>
              <p className="text-sm text-ink/60">{m.procSuppliersSee}</p>
              {objects.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={item.id === projectId ? primary : ghost}
                  disabled={sendForm.submitting}
                  onClick={() => sendTo(item.id)}
                >
                  <span className="grid text-center">
                    <span className="break-words">{item.title}</span>
                    {item.id === projectId ? <span className="text-xs opacity-80">{m.procThisObject}</span> : null}
                  </span>
                </button>
              ))}
            </div>
          ) : null}
          {screen.step === 1 ? (
            <details className="rounded-2xl border border-ink/10 bg-white/70 px-4 py-1">
              <summary className="cursor-pointer py-3 text-sm">{m.procMore}</summary>
              <div className="pb-4">
                <StatementImport
                  m={m}
                  resolveId={async () => {
                    const created = await createProcRequest(projectId, m.procStatement, crypto.randomUUID());
                    return created.id;
                  }}
                  onSaved={reload}
                />
              </div>
            </details>
          ) : null}
        </section>
      ) : null}

      {screen.kind === "edit" ? (
        <section className="grid gap-3">
          <button type="button" className="w-fit text-sm underline" onClick={() => setScreen({ kind: "ask", step: 1 })}>
            {m.procBack}
          </button>
          <h2 className="break-words text-xl font-medium">{screen.title}</h2>
          <p className="text-sm text-ink/60">{m.procEditRepeat}</p>
          <p className="text-sm text-ink/60">{m.procSuppliersSee}</p>
          {screen.lines.map((line) => (
            <label key={line.id} className="grid gap-1 text-sm">
              <span className="break-words font-medium">
                {line.title} · {line.unit}
              </span>
              <input
                value={line.qty}
                inputMode="decimal"
                aria-label={`${m.procQty} ${line.title}`}
                className={field}
                onChange={(event) => {
                  const value = event.target.value;
                  setScreen((prev) =>
                    prev.kind === "edit"
                      ? { ...prev, lines: prev.lines.map((item) => (item.id === line.id ? { ...item, qty: value } : item)) }
                      : prev,
                  );
                }}
              />
            </label>
          ))}
          <button
            type="button"
            className={primary}
            disabled={saveForm.submitting}
            onClick={() =>
              void saveForm.submit(async () => {
                if (screen.kind !== "edit") return;
                const next = screen.lines.map((line) => {
                  const amount = parseQty(line.qty);
                  if (amount == null) throw new Error(m.procErrQty);
                  return { id: line.id, qty: amount };
                });
                await Promise.all(next.map((line) => patchProcLine(line.id, line.qty)));
              })
            }
          >
            {m.procQtySave}
          </button>
        </section>
      ) : null}

      {screen.kind === "prices" ? (
        <section className="grid min-w-0 gap-3">
          <button type="button" className="w-fit text-sm underline" onClick={() => setScreen({ kind: "ask", step: 1 })}>
            {m.procBack}
          </button>
          {sheetQuery.loading || !sheet ? (
            sheetQuery.status === "error" ? (
              <ErrorRetry message={m.hubLoadError} retryLabel={m.hubRetry} onRetry={sheetQuery.reload} />
            ) : (
              <LoadingSkeleton label={m.hubLoading} />
            )
          ) : (
            <>
              <div>
                <h2 className="break-words text-xl font-medium">
                  {sheet.request.number}. {sheet.request.title}
                </h2>
                <p className="text-sm text-ink/60">
                  {requestStatus(sheet.request.status, m)} ·{" "}
                  {fill(m.procSummary, {
                    n: sheet.summary.lines,
                    k: sheet.summary.closed,
                    m: sheet.summary.no_price,
                  })}
                </p>
              </div>
              {access.can_decide ? (
                <button
                  type="button"
                  className={primary}
                  disabled={winnerForm.submitting || sheet.lines.every((line) => !line.best_offer_id)}
                  onClick={() =>
                    void winnerForm.submit(async (key) => {
                      await selectProcBest(priceId || sheet.request.id, key);
                    })
                  }
                >
                  {m.procWinnerBtn}
                </button>
              ) : null}
              <div className="max-w-full overflow-x-auto rounded-2xl border border-ink/10">
                <table className="w-max min-w-full border-separate border-spacing-0 text-sm">
                  <thead>
                    <tr>
                      <th className="sticky left-0 z-20 min-w-[8rem] max-w-[10rem] bg-paper px-3 py-3 text-left">{m.procLine}</th>
                      {sheet.suppliers.map((item) => (
                        <th key={item.name} className="min-w-36 bg-paper px-3 py-3 text-left font-medium">
                          {item.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sheet.lines.map((line) => (
                      <tr key={line.id}>
                        <th className="sticky left-0 z-10 min-w-[8rem] max-w-[10rem] bg-paper px-3 py-3 text-left align-top font-normal">
                          <span className="block break-words font-medium">{line.title}</span>
                          <span className="text-xs text-ink/60">
                            {line.qty} {line.unit} · {statusText(line.status_code, m)}
                          </span>
                        </th>
                        {sheet.suppliers.map((item) => {
                          const offer = line.cells[item.name] || null;
                          return (
                            <td
                              key={item.name}
                              className={`px-3 py-3 align-top ${offer?.is_best ? "bg-emerald-100" : ""}`}
                            >
                              {priceCell(offer, line.qty)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                    <tr>
                      <th className="sticky left-0 z-10 bg-paper px-3 py-3 text-left">{m.procTotal}</th>
                      {sheet.suppliers.map((item) => (
                        <td key={item.name} className="px-3 py-3 font-medium">
                          {tenge(item.total_kzt, locale)}
                          {item.vat_mixed ? <span className="mt-1 block text-xs font-normal text-ink/60">{m.procVatMixed}</span> : null}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
              <details className="rounded-2xl border border-ink/10 bg-white/70 px-4 py-1">
                <summary className="cursor-pointer py-3 text-sm">{m.procMore}</summary>
                <div className="grid gap-4 pb-4">
                  {access.can_request ? (
                    <StatementImport m={m} resolveId={async () => sheet.request.id} onSaved={reload} />
                  ) : null}
                  <button
                    type="button"
                    className={ghost}
                    onClick={() =>
                      void run(() =>
                        downloadProc(
                          `/v1/procurement/requests/${sheet.request.id}/export.xlsx`,
                          `comparison-${sheet.request.number}.xlsx`,
                        ),
                      )
                    }
                  >
                    {m.procExport}
                  </button>
                  {access.can_offer ? (
                    <div className="grid gap-3">
                      <h3 className="font-medium">{m.procOffersTitle}</h3>
                      {sheet.lines.length === 0 ? <p className="text-sm text-ink/60">{m.procNeedLines}</p> : null}
                      {sheet.lines.length > 1 ? (
                        <label className="grid gap-1 text-sm">
                          {m.procLine}
                          <select value={lineId} onChange={(event) => setLineId(event.target.value)} className={field}>
                            {sheet.lines.map((line) => (
                              <option key={line.id} value={line.id}>
                                {line.pos_no}. {line.title}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      <label className="grid gap-1 text-sm">
                        {m.procSupplier}
                        <input value={supplier} onChange={(event) => setSupplier(event.target.value)} className={field} />
                      </label>
                      <label className="grid gap-1 text-sm">
                        {m.procPrice}
                        <input value={price} onChange={(event) => setPrice(event.target.value)} inputMode="decimal" className={field} />
                      </label>
                      <label className="grid gap-1 text-sm">
                        {m.procVat}
                        <select value={vat} onChange={(event) => setVat(event.target.value as "yes" | "no" | "unknown")} className={field}>
                          <option value="yes">{m.procVatYes}</option>
                          <option value="no">{m.procVatNo}</option>
                          <option value="unknown">{m.procVatUnknown}</option>
                        </select>
                      </label>
                      <details>
                        <summary className="cursor-pointer py-2 text-sm">{m.procAdvanced}</summary>
                        <div className="mt-2 grid gap-3">
                          <label className="grid gap-1 text-sm">
                            {m.procDelivery}
                            <input value={delivery} onChange={(event) => setDelivery(event.target.value)} className={field} />
                          </label>
                          <label className="grid gap-1 text-sm">
                            {m.procComment}
                            <input value={comment} onChange={(event) => setComment(event.target.value)} className={field} />
                          </label>
                          <label className="flex min-h-12 items-center gap-2 text-sm">
                            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                            {m.procConfirmed}
                          </label>
                        </div>
                      </details>
                      <button
                        type="button"
                        className={ghost}
                        disabled={offerForm.submitting || !lineId}
                        onClick={() =>
                          void offerForm.submit(async (key) => {
                            const amount = parseQty(price);
                            if (!supplier.trim()) throw new Error(m.procErrSupplier);
                            if (amount == null) throw new Error(m.procErrPrice);
                            await createProcOffer(
                              lineId,
                              {
                                supplier_name: supplier.trim(),
                                price_kzt: amount,
                                vat_included: vat === "unknown" ? null : vat === "yes",
                                delivery_term: delivery,
                                note: comment,
                                confirmed,
                              },
                              key,
                            );
                            setPrice("");
                          })
                        }
                      >
                        {m.procAddOffer}
                      </button>
                      <label className="grid gap-1 text-sm">
                        {m.procSupplierFile}
                        <input value={fileSupplier} onChange={(event) => setFileSupplier(event.target.value)} className={field} />
                      </label>
                      <label className="grid gap-1 text-sm">
                        {m.procUploadOffers}
                        <input
                          type="file"
                          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                          className="block w-full text-sm"
                          onChange={(event) => {
                            const file = event.target.files?.[0];
                            event.target.value = "";
                            if (!file) return;
                            void run(async () => {
                              const result = await importProcOffers(sheet.request.id, file, fileSupplier, crypto.randomUUID());
                              const problems = result.warnings
                                .map((item) => `${m.procRow} ${item.row}: ${issueText(item.code, m)}`)
                                .join(". ");
                              toast(problems || m.procImportSaved);
                              reload();
                            });
                          }}
                        />
                      </label>
                      <button
                        type="button"
                        className={`${ghost} sm:w-auto`}
                        onClick={() => void run(() => downloadProc("/v1/procurement/offers-template.xlsx", "offers-template.xlsx"))}
                      >
                        {m.procTemplate}
                      </button>
                      {sheet.lines.flatMap((line) => line.offers).map((offer) => (
                        <p key={offer.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <span className="min-w-0 break-words">
                            {offer.supplier_name} · {tenge(offer.price_kzt, locale)}
                          </span>
                          <button
                            type="button"
                            className="underline"
                            onClick={() =>
                              void run(async () => {
                                await deleteProcOffer(offer.id);
                                reload();
                              })
                            }
                          >
                            {m.procRemove}
                          </button>
                        </p>
                      ))}
                    </div>
                  ) : null}
                  {access.can_invoice ? (
                    <div className="grid gap-3">
                      <h3 className="font-medium">{m.procInvoice}</h3>
                      {duplicate ? <p className="text-sm text-ink/50">{m.procDuplicate}</p> : null}
                      {versionId ? (
                        <p className="text-sm text-ink/50">
                          {m.procNewVersion}{" "}
                          <button
                            type="button"
                            className="underline"
                            onClick={() =>
                              void run(async () => {
                                await setProcDocumentActual(versionId, true);
                                setVersionId(null);
                                reload();
                              })
                            }
                          >
                            {m.procActual}
                          </button>
                        </p>
                      ) : null}
                      <label className="grid gap-1 text-sm">
                        {m.procSupplier}
                        <input value={invoiceSupplier} onChange={(event) => setInvoiceSupplier(event.target.value)} className={field} />
                      </label>
                      <label className="grid gap-1 text-sm">
                        {m.procInvoiceNumber}
                        <input value={invoiceNumber} onChange={(event) => setInvoiceNumber(event.target.value)} className={field} />
                      </label>
                      <label className="grid gap-1 text-sm">
                        {m.procInvoiceDate}
                        <input type="date" value={invoiceDate} onChange={(event) => setInvoiceDate(event.target.value)} className={field} />
                      </label>
                      <label className="grid gap-1 text-sm">
                        {m.procInvoiceAmount}
                        <input value={invoiceAmount} onChange={(event) => setInvoiceAmount(event.target.value)} inputMode="decimal" className={field} />
                      </label>
                      <label className="grid gap-1 text-sm">
                        {m.procAttach}
                        <input
                          type="file"
                          accept="application/pdf,image/jpeg,image/png,image/webp"
                          className="block w-full text-sm"
                          onChange={(event) => {
                            const file = event.target.files?.[0];
                            event.target.value = "";
                            if (!file || !priceId) return;
                            if (!invoiceSupplier.trim()) {
                              toast(m.procErrSupplier);
                              return;
                            }
                            void run(async () => {
                              const result = await uploadProcDocument(
                                priceId,
                                file,
                                {
                                  supplier_name: invoiceSupplier,
                                  doc_number: invoiceNumber,
                                  doc_date: invoiceDate,
                                  amount_kzt: invoiceAmount,
                                },
                                crypto.randomUUID(),
                              );
                              setDuplicate(result.duplicate);
                              setVersionId(result.new_version_of_supplier ? result.document.id : null);
                              reload();
                            });
                          }}
                        />
                      </label>
                      {sheet.documents.map((doc) => (
                        <p key={doc.id} className="break-words text-sm text-ink/60">
                          <button
                            type="button"
                            className="underline"
                            onClick={() =>
                              void openProcFile(`/v1/procurement/documents/${doc.id}/file`).catch((err: unknown) =>
                                toast(err instanceof Error ? err.message : m.hubSaveError),
                              )
                            }
                          >
                            {doc.supplier_name}
                            {doc.doc_number ? ` · ${doc.doc_number}` : ""}
                          </button>
                          {doc.duplicate_of ? ` · ${m.procDuplicate}` : ""}
                          {!doc.is_actual ? ` · ${m.procNotActual}` : ""}
                        </p>
                      ))}
                    </div>
                  ) : null}
                </div>
              </details>
            </>
          )}
        </section>
      ) : null}

      {screen.kind === "ask" && screen.step === 1 ? (
        <section className="grid gap-3">
          {requests.length === 0 ? <p className="text-sm text-ink/60">{m.procEmpty}</p> : null}
          {requests.map((item) => (
            <article key={item.id} className="grid gap-2 rounded-2xl border border-ink/10 bg-white/70 p-3">
              <h3 className="break-words font-medium">
                {item.number}. {item.title}
              </h3>
              <p className="text-sm text-ink/60">
                {requestStatus(item.status, m)} · {item.lines} {m.procLinesCount}
              </p>
              {access.can_request ? (
                <button
                  type="button"
                  className={primary}
                  disabled={repeatForm.submitting}
                  onClick={() =>
                    void repeatForm.submit(async (key) => {
                      const result = await repeatProcRequest(item.id, key);
                      setScreen({
                        kind: "edit",
                        title: result.request.title,
                        lines: result.lines.map((line) => ({
                          id: line.id,
                          title: line.title,
                          unit: line.unit,
                          qty: String(line.qty),
                        })),
                      });
                    })
                  }
                >
                  {m.procRepeat}
                </button>
              ) : null}
              <button
                type="button"
                className={ghost}
                onClick={() => {
                  setDuplicate(false);
                  setVersionId(null);
                  setScreen({ kind: "prices", requestId: item.id });
                }}
              >
                {m.procPrices}
              </button>
            </article>
          ))}
        </section>
      ) : null}
    </div>
  );
}
