"use client";

import { useRef, useState } from "react";
import { importProcLines } from "@/lib/api";
import { useMessages } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import type { ProcImportResult } from "@/lib/types";

const ghost =
  "inline-flex min-h-12 w-full items-center justify-center rounded-full border border-ink/15 bg-white px-4 text-sm disabled:opacity-50";

function issueText(code: string, m: ReturnType<typeof useMessages>) {
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

export function StatementImport({
  resolveId,
  onSaved,
}: {
  resolveId: () => Promise<string>;
  onSaved: () => void;
}) {
  const m = useMessages();
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
            <p key={row.row} className={`long-row break-words text-sm ${row.errors.length ? "text-red-800" : "text-ink/80"}`}>
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
