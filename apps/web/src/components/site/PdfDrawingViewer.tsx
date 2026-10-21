"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { Locale } from "@/lib/types";
import { t } from "@/i18n/messages";

type Props = {
  locale: Locale;
  fileKey: string;
  loadFile: (signal: AbortSignal) => Promise<ArrayBuffer>;
};

export const DRAWING_VIEW_TIMEOUT_MS = 12_000;
const WORKER_URL = "/pdf.worker.min.mjs";

export function PdfDrawingViewer({ locale, fileKey, loadFile }: Props) {
  const m = t(locale);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const scaleRef = useRef(1);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pageNum, setPageNum] = useState(1);
  const [scale, setScale] = useState(1);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [painted, setPainted] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);

  useEffect(() => {
    let cancelled = false;
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), DRAWING_VIEW_TIMEOUT_MS);
    let task: { destroy: () => Promise<void> } | null = null;
    setLoading(true);
    setFailed(false);
    setPainted(false);
    setPdfDoc(null);

    (async () => {
      try {
        const bytes = await Promise.race([
          loadFile(timeout.signal),
          abortError(timeout.signal, DRAWING_VIEW_TIMEOUT_MS),
        ]);
        if (cancelled || timeout.signal.aborted) throw new Error("timeout");
        const worker = await fetch(WORKER_URL, { signal: timeout.signal, cache: "force-cache" });
        if (!worker.ok) throw new Error("worker");
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = WORKER_URL;
        const loadingTask = pdfjs.getDocument({ data: new Uint8Array(bytes) });
        task = loadingTask;
        const doc = await loadingTask.promise;
        if (cancelled) {
          await loadingTask.destroy();
          return;
        }
        setPdfDoc(doc);
        setPageNum(1);
        setLoading(false);
      } catch {
        if (cancelled) return;
        setFailed(true);
        setLoading(false);
      } finally {
        clearTimeout(timer);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      timeout.abort();
      void task?.destroy().catch(() => undefined);
    };
  }, [attempt, fileKey, loadFile]);

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    let start = 0;
    let base = 1;
    const distance = (ev: TouchEvent) => {
      const [a, b] = [ev.touches[0], ev.touches[1]];
      return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
    };
    const onStart = (ev: TouchEvent) => {
      if (ev.touches.length === 2) {
        start = distance(ev);
        base = scaleRef.current;
      }
    };
    const onMove = (ev: TouchEvent) => {
      if (ev.touches.length !== 2 || !start) return;
      ev.preventDefault();
      const next = Math.min(4, Math.max(0.5, base * (distance(ev) / start)));
      setScale(Number(next.toFixed(2)));
    };
    box.addEventListener("touchstart", onStart, { passive: true });
    box.addEventListener("touchmove", onMove, { passive: false });
    return () => {
      box.removeEventListener("touchstart", onStart);
      box.removeEventListener("touchmove", onMove);
    };
  }, []);

  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;
    let cancel = false;
    const doc = pdfDoc;
    (async () => {
      const page = await doc.getPage(pageNum);
      if (cancel) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      const context = canvas.getContext("2d");
      if (!context) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvas, canvasContext: context, viewport }).promise;
      if (!cancel) setPainted(true);
    })().catch(() => {
      if (!cancel) setFailed(true);
    });
    return () => {
      cancel = true;
    };
  }, [pdfDoc, pageNum, scale]);

  const fit = useCallback(() => {
    const box = boxRef.current;
    const canvas = canvasRef.current;
    if (!box || !canvas || !canvas.width) return;
    const next = Math.max(0.5, (box.clientWidth - 16) / (canvas.width / scaleRef.current));
    setScale(Number(next.toFixed(2)));
  }, []);

  const pages = pdfDoc?.numPages ?? 1;
  return (
    <div className="overflow-hidden rounded-sm border border-ink/10 bg-[#1A1F29] text-paper">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
        <button type="button" className="min-h-12 px-3" disabled={pageNum <= 1} onClick={() => setPageNum((n) => Math.max(1, n - 1))}>
          {"\u003c"}
        </button>
        <span>{m.drawPage.replace("{page}", String(pageNum)).replace("{total}", String(pages))}</span>
        <button type="button" className="min-h-12 px-3" disabled={pageNum >= pages} onClick={() => setPageNum((n) => Math.min(pages, n + 1))}>
          {">"}
        </button>
        <button type="button" className="min-h-12 px-3" aria-label={m.drawZoomOut} onClick={() => setScale((n) => Math.max(0.5, Number((n - 0.2).toFixed(2))))}>
          -
        </button>
        <button type="button" className="min-h-12 px-3" aria-label={m.drawZoomIn} onClick={() => setScale((n) => Math.min(4, Number((n + 0.2).toFixed(2))))}>
          +
        </button>
        <button type="button" className="min-h-12 px-3" onClick={fit}>
          {m.drawFit}
        </button>
      </div>
      <div ref={boxRef} className="relative max-h-52 min-h-32 overflow-auto p-3" style={{ touchAction: "none" }}>
        {loading ? <p className="text-xs text-paper/70">{m.drawLoading}</p> : null}
        {failed ? (
          <div role="alert" className="grid justify-items-start gap-2">
            <p className="text-xs text-clay">{m.drawError}</p>
            <button
              type="button"
              className="inline-flex min-h-12 items-center rounded-full bg-paper px-4 text-sm font-medium text-ink"
              onClick={() => setAttempt((n) => n + 1)}
            >
              {m.drawRetry}
            </button>
          </div>
        ) : null}
        <canvas ref={canvasRef} className={painted && !failed ? "mx-auto block max-w-none bg-white" : "hidden"} />
      </div>
    </div>
  );
}

function abortError(signal: AbortSignal, ms: number): Promise<never> {
  return new Promise((_, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    const stop = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    if (signal.aborted) {
      stop();
      return;
    }
    signal.addEventListener("abort", stop, { once: true });
  });
}
