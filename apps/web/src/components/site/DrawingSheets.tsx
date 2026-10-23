"use client";

import { useCallback, useEffect, useState } from "react";
import { t } from "@/i18n/messages";
import { apiFetch, fetchAuthorizedBlob } from "@/lib/api";
import {
  drawingCreatePath,
  drawingFilePath,
  drawingRevisionPath,
  drawingSheetsPath,
  gateStatus,
  hasNewerVersion,
  sheetTitle,
  type DrawingSheet,
} from "@/lib/drawings";
import type { Locale } from "@/lib/types";
import { PdfDrawingViewer } from "./PdfDrawingViewer";

type ListPayload = { can_upload: boolean; sheets: DrawingSheet[] };

export function DrawingSheets({ locale, projectId }: { locale: Locale; projectId: string }) {
  const m = t(locale);
  const [sheets, setSheets] = useState<DrawingSheet[]>([]);
  const [canUpload, setCanUpload] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [selectedRev, setSelectedRev] = useState("");
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(false);

  const load = useCallback(async () => {
    const res = await apiFetch(drawingSheetsPath(projectId));
    if (!res.ok) {
      if (gateStatus(res.status) === "hidden") setHidden(true);
      else setError(m.drawError);
      return;
    }
    const body = (await res.json()) as { data: ListPayload };
    const next = body.data.sheets || [];
    setSheets(next);
    setCanUpload(Boolean(body.data.can_upload));
    setHidden(false);
    setSelectedId((current) => current || next[0]?.id || "");
    setSelectedRev((current) => current || next[0]?.current_rev || "");
  }, [m.drawError, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = sheets.find((item) => item.id === selectedId) || null;
  const rev = selectedRev || selected?.current_rev || "";
  const newer = selected ? hasNewerVersion(selected.revisions, rev) : false;

  async function send(path: string, file: File, fields: Record<string, string>) {
    setError("");
    const body = new FormData();
    body.append("file", file);
    body.append("title", sheetTitle(file.name));
    for (const [key, value] of Object.entries(fields)) body.append(key, value);
    const res = await apiFetch(path, { method: "POST", body });
    const status = gateStatus(res.status);
    if (status === "hidden") {
      setHidden(true);
      return;
    }
    if (status === "conflict") {
      setError(m.drawConflict);
      await load();
      return;
    }
    if (!res.ok) {
      setError(res.status === 400 ? m.drawPdfOnly : m.drawError);
      return;
    }
    const saved = (await res.json()) as { data: DrawingSheet };
    setSelectedId(saved.data.id);
    setSelectedRev(saved.data.current_rev);
    await load();
  }

  async function onCreate(file: File | undefined) {
    if (!file) return;
    await send(drawingCreatePath(projectId), file, {
      id: crypto.randomUUID(),
      revision_id: crypto.randomUUID(),
      file_id: crypto.randomUUID(),
      row_version: "0",
    });
  }

  async function onRevise(file: File | undefined) {
    if (!file || !selected) return;
    await send(drawingRevisionPath(selected.id), file, {
      id: crypto.randomUUID(),
      file_id: crypto.randomUUID(),
      row_version: String(selected.row_version),
    });
  }

  const fileId = selected?.id || "";
  const loadFile = useCallback(
    (signal: AbortSignal) => {
      if (!fileId || !rev) return Promise.reject(new Error("empty"));
      return fetchAuthorizedBlob(drawingFilePath(fileId, rev), signal).then((blob) => blob.arrayBuffer());
    },
    [fileId, rev],
  );

  if (hidden) return null;

  const upload = canUpload ? (
    <label className="inline-flex min-h-12 cursor-pointer items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper">
      {sheets.length === 0 ? m.drawEmpty : m.drawUpload}
      <input
        type="file"
        accept="application/pdf"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          void onCreate(file);
        }}
      />
    </label>
  ) : null;

  return (
    <section className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-medium">{m.tabDraw}</h2>
        {sheets.length > 0 ? upload : null}
      </div>
      {error ? <p className="text-sm text-clay">{error}</p> : null}
      {sheets.length === 0 ? (
        <div className="border border-dashed border-ink/20 p-6 text-center">
          {canUpload ? upload : <p className="text-sm">{m.drawEmpty}</p>}
        </div>
      ) : (
        <div className="grid gap-3">
          <div className="flex gap-2 overflow-x-auto">
            {sheets.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`min-h-12 shrink-0 rounded-full px-3 text-sm ${item.id === selected?.id ? "bg-pine text-paper" : "border border-ink/15"}`}
                onClick={() => {
                  setSelectedId(item.id);
                  setSelectedRev(item.current_rev);
                }}
              >
                {item.code} · {item.title}
              </button>
            ))}
          </div>
          {newer ? (
            <div className="flex items-center justify-between gap-3 rounded-sm bg-sand/40 px-3 py-2">
              <p className="text-sm font-medium">{m.drawNewer}</p>
              <button
                type="button"
                className="inline-flex min-h-12 shrink-0 items-center rounded-full bg-pine px-4 text-sm font-medium text-paper"
                onClick={() => selected && setSelectedRev(selected.current_rev)}
              >
                {m.drawOpen}
              </button>
            </div>
          ) : null}
          {selected && rev ? <PdfDrawingViewer locale={locale} fileKey={`${selected.id}:${rev}`} loadFile={loadFile} /> : null}
          {selected ? (
            <div className="grid gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wide text-ink/50">{m.drawArchive}</p>
                {canUpload ? (
                  <label className="inline-flex min-h-12 cursor-pointer items-center text-sm underline">
                    {m.drawNewRev}
                    <input
                      type="file"
                      accept="application/pdf"
                      className="sr-only"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        event.target.value = "";
                        void onRevise(file);
                      }}
                    />
                  </label>
                ) : null}
              </div>
              <div className="flex gap-2 overflow-x-auto">
                {selected.revisions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`min-h-12 shrink-0 rounded-full px-3 text-sm ${item.rev === rev ? "bg-ink text-paper" : "border border-ink/15"}`}
                    onClick={() => setSelectedRev(item.rev)}
                  >
                    {m.drawRev} {item.rev}
                    {item.is_current ? ` · ${m.drawCurrent}` : ""}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
