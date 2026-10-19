"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { Locale } from "@/lib/types";
import { t } from "@/i18n/messages";

type Props = {
  locale: Locale;
  fileKey: string;
  loadFile: () => Promise<ArrayBuffer>;
  overlay?: ReactNode;
};

export function PdfDrawingViewer({ locale, fileKey, loadFile, overlay }: Props) {
  const m = t(locale);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const scaleRef = useRef(1);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pageNum, setPageNum] = useState(1);
  const [scale, setScale] = useState(1);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setFailed(false);
    setPdfDoc(null);
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const data = new Uint8Array(await loadFile());
        const doc = await pdfjs.getDocument({ data }).promise;
        if (!alive) return;
        setPdfDoc(doc);
        setPageNum(1);
        setLoading(false);
      } catch {
        if (!alive) return;
        setFailed(true);
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [fileKey, loadFile]);

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
    (async () => {
      const page = await pdfDoc.getPage(pageNum);
      if (cancel) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      const context = canvas.getContext("2d");
      if (!context) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: context, viewport } as never).promise;
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
          {"<"}
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
      <div ref={boxRef} className="relative min-h-64 overflow-auto p-3" style={{ touchAction: "none" }}>
        {loading ? <p className="text-xs text-paper/70">{m.drawLoading}</p> : null}
        {failed ? <p className="text-xs text-clay">{m.drawError}</p> : null}
        <div className="relative mx-auto inline-block max-w-none">
          <canvas ref={canvasRef} className="block max-w-none bg-white" />
          {overlay ? <div className="pointer-events-none absolute inset-0">{overlay}</div> : null}
        </div>
      </div>
    </div>
  );
}
