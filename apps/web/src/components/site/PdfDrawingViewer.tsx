"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { Locale } from "@/lib/types";

interface DrawingItem {
  id: string;
  code: string;
  title: string;
  revision: string;
  current: boolean;
  file?: string;
}

interface Props {
  locale: Locale;
  drawings: DrawingItem[];
  selectedDrawing: DrawingItem | null;
  onSelectDrawing: (d: DrawingItem) => void;
  projectTitle?: string;
}

export function PdfDrawingViewer({
  locale,
  drawings,
  selectedDrawing,
  onSelectDrawing,
  projectTitle = "ИЖС Бесагаш",
}: Props) {
  const isKk = locale === "kk";
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [pageNum, setPageNum] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [scale, setScale] = useState(1.2);
  const [rotation, setRotation] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customPdfName, setCustomPdfName] = useState<string | null>(null);

  // Generate synthetic CAD blueprint PDF using jsPDF for default demo
  const generateSampleCadPdf = useCallback(async (drawing: DrawingItem | null): Promise<ArrayBuffer> => {
    const { jsPDF } = await import("jspdf");
    // A2 landscape drawing canvas in mm: 594 x 420
    const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a3" });
    const code = drawing?.code || "АР-01";
    const title = drawing?.title || "План 1-го этажа";
    const rev = drawing?.revision || "A";

    // Blueprint dark-blue background
    doc.setFillColor(24, 38, 62);
    doc.rect(0, 0, 420, 297, "F");

    // Grid lines (subtle cyan)
    doc.setDrawColor(36, 62, 98);
    doc.setLineWidth(0.2);
    for (let x = 10; x < 410; x += 10) {
      doc.line(x, 10, x, 287);
    }
    for (let y = 10; y < 287; y += 10) {
      doc.line(10, y, 410, y);
    }

    // Outer Border & Margin
    doc.setDrawColor(0, 200, 255);
    doc.setLineWidth(0.8);
    doc.rect(15, 15, 390, 267);

    // Inner Border
    doc.setLineWidth(0.3);
    doc.rect(20, 20, 380, 257);

    // Architectural Drawing Geometry
    // Outer Walls
    doc.setDrawColor(255, 255, 255);
    doc.setLineWidth(1.2);
    doc.rect(60, 60, 240, 160);

    // Inner partitions
    doc.setLineWidth(0.6);
    doc.line(180, 60, 180, 220); // main partition
    doc.line(60, 140, 180, 140); // bedroom partition
    doc.line(180, 130, 300, 130); // kitchen / living partition

    // Dimension lines
    doc.setDrawColor(0, 240, 255);
    doc.setLineWidth(0.2);
    // Top dimension
    doc.line(60, 45, 300, 45);
    doc.line(60, 42, 60, 48);
    doc.line(180, 42, 180, 48);
    doc.line(300, 42, 300, 48);
    doc.setTextColor(0, 240, 255);
    doc.setFontSize(8);
    doc.text("6 000", 115, 43);
    doc.text("6 000", 235, 43);
    doc.text("12 000 (Общая длина)", 165, 38);

    // Left dimension
    doc.line(45, 60, 45, 220);
    doc.line(42, 60, 48, 60);
    doc.line(42, 140, 48, 140);
    doc.line(42, 220, 48, 220);
    doc.text("4 000", 35, 105, { angle: 90 });
    doc.text("4 000", 35, 185, { angle: 90 });

    // Room labels
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(11);
    doc.text("1. ГОСТИНАЯ / LIVING", 80, 95);
    doc.setFontSize(8);
    doc.setTextColor(180, 220, 255);
    doc.text("S = 38.4 m2  ·  h = 3.20m", 80, 102);

    doc.setFontSize(11);
    doc.setTextColor(255, 255, 255);
    doc.text("2. МАСТЕР-СПАЛЬНЯ", 80, 175);
    doc.setFontSize(8);
    doc.setTextColor(180, 220, 255);
    doc.text("S = 24.6 m2  ·  h = 3.20m", 80, 182);

    doc.setFontSize(11);
    doc.setTextColor(255, 255, 255);
    doc.text("3. КУХНЯ-СТОЛОВАЯ", 200, 95);
    doc.setFontSize(8);
    doc.setTextColor(180, 220, 255);
    doc.text("S = 28.2 m2  ·  h = 3.20m", 200, 102);

    doc.setFontSize(11);
    doc.setTextColor(255, 255, 255);
    doc.text("4. ХОЛЛ / ПРИХОЖАЯ & С/У", 200, 175);
    doc.setFontSize(8);
    doc.setTextColor(180, 220, 255);
    doc.text("S = 22.0 m2  ·  h = 3.20m", 200, 182);

    // North arrow / Compass
    doc.setDrawColor(255, 215, 0);
    doc.setLineWidth(0.8);
    doc.circle(360, 60, 14);
    doc.line(360, 46, 360, 74);
    doc.line(346, 60, 374, 60);
    doc.setTextColor(255, 215, 0);
    doc.setFontSize(10);
    doc.text("N", 358, 43);

    // Official CAD Stamp (Title Block) in bottom right
    const tbX = 260;
    const tbY = 225;
    const tbW = 140;
    const tbH = 52;
    doc.setDrawColor(0, 200, 255);
    doc.setLineWidth(0.6);
    doc.rect(tbX, tbY, tbW, tbH);
    doc.line(tbX, tbY + 12, tbX + tbW, tbY + 12);
    doc.line(tbX, tbY + 26, tbX + tbW, tbY + 26);
    doc.line(tbX, tbY + 38, tbX + tbW, tbY + 38);
    doc.line(tbX + 70, tbY, tbX + 70, tbY + tbH);

    doc.setFontSize(7);
    doc.setTextColor(150, 180, 220);
    doc.text("ОБЪЕКТ:", tbX + 3, tbY + 5);
    doc.text("РАЗДЕЛ:", tbX + 73, tbY + 5);
    doc.text("ГИП / АРХИТЕКТОР:", tbX + 3, tbY + 17);
    doc.text("ЛИСТ / РЕВИЗИЯ:", tbX + 73, tbY + 17);
    doc.text("СТАДИЯ:", tbX + 3, tbY + 31);
    doc.text("МАСШТАБ:", tbX + 73, tbY + 31);
    doc.text("ОРГАНИЗАЦИЯ:", tbX + 3, tbY + 43);

    doc.setFontSize(8);
    doc.setTextColor(255, 255, 255);
    doc.text(projectTitle.substring(0, 24), tbX + 3, tbY + 10);
    doc.text(`${code} Комплект`, tbX + 73, tbY + 10);
    doc.text("Бекенов А.М. (Bek Arch)", tbX + 3, tbY + 22);
    doc.text(`Лист 1 · Рев. ${rev}`, tbX + 73, tbY + 22);
    doc.text("РП (Рабочий проект)", tbX + 3, tbY + 36);
    doc.text("1:100", tbX + 73, tbY + 36);
    doc.text("ANYQ ConTech Platform", tbX + 3, tbY + 49);

    return doc.output("arraybuffer");
  }, [projectTitle]);

  // Load PDF into PDF.js
  const loadPdf = useCallback(async (source: ArrayBuffer | string) => {
    setLoading(true);
    setError(null);
    try {
      const pdfjs = await import("pdfjs-dist");
      if (!pdfjs.GlobalWorkerOptions.workerSrc) {
        pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
      }

      const loadingTask = typeof source === "string"
        ? pdfjs.getDocument({ url: source })
        : pdfjs.getDocument({ data: source } as any);

      const doc = await loadingTask.promise;
      setPdfDoc(doc);
      setTotalPages(doc.numPages);
      setPageNum(1);
      setLoading(false);
    } catch (err: any) {
      console.error("PDF.js load error:", err);
      setError(err?.message || "Ошибка загрузки чертежа");
      setLoading(false);
    }
  }, []);

  // Initial load when drawing selection changes
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const buffer = await generateSampleCadPdf(selectedDrawing);
        if (active) {
          loadPdf(buffer);
        }
      } catch (e: any) {
        if (active) setError(e.message);
      }
    })();
    return () => { active = false; };
  }, [selectedDrawing, generateSampleCadPdf, loadPdf]);

  // Render current page onto canvas
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;
    let cancelRender = false;

    (async () => {
      try {
        const page = await pdfDoc.getPage(pageNum);
        if (cancelRender) return;

        const viewport = page.getViewport({ scale, rotation });
        const canvas = canvasRef.current;
        if (!canvas) return;

        const context = canvas.getContext("2d");
        if (!context) return;

        canvas.width = viewport.width;
        canvas.height = viewport.height;

        const renderContext = {
          canvasContext: context,
          viewport,
        };

        await page.render(renderContext).promise;
      } catch (err) {
        console.error("Page render error:", err);
      }
    })();

    return () => {
      cancelRender = true;
    };
  }, [pdfDoc, pageNum, scale, rotation]);

  // File upload handler
  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCustomPdfName(file.name);
    const buffer = await file.arrayBuffer();
    loadPdf(buffer);
  }

  function handleFitWidth() {
    if (containerRef.current) {
      const containerWidth = containerRef.current.clientWidth - 48;
      // assuming standard landscape ratio ~1.4
      const targetScale = Math.max(0.6, containerWidth / 800);
      setScale(Number(targetScale.toFixed(2)));
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 border-t border-ink/10 min-h-[580px] bg-paper">
      {/* Left Drawings List (4 cols) */}
      <div className="lg:col-span-4 p-4 border-r border-ink/10 bg-paper space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-xs text-ink/60 uppercase tracking-wider">
            {isKk ? "Сызбалар тізімі (PDF.js)" : "Комплект чертежей (PDF.js)"}
          </h3>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-pine/10 text-pine font-bold font-mono">
            Mozilla PDF.js
          </span>
        </div>

        {/* Custom file upload button */}
        <label className="flex items-center justify-center gap-2 p-2.5 border-2 border-dashed border-pine/40 rounded-xl bg-pine/5 hover:bg-pine/10 cursor-pointer text-xs font-semibold text-pine transition-colors">
          <span>📁 Загрузить свой PDF / Чертеж</span>
          <input type="file" accept="application/pdf" className="hidden" onChange={handleFileUpload} />
        </label>
        {customPdfName && (
          <p className="text-[11px] text-pine/80 truncate">
            ✓ Загружен: <b>{customPdfName}</b>
          </p>
        )}

        <div className="space-y-2">
          {drawings.map((d) => (
            <div
              key={d.id}
              onClick={() => {
                setCustomPdfName(null);
                onSelectDrawing(d);
              }}
              className={`p-3 rounded-xl border transition-all cursor-pointer text-xs ${
                selectedDrawing?.id === d.id && !customPdfName
                  ? "bg-pine/10 border-pine font-medium shadow-xs"
                  : "border-ink/10 hover:bg-mist/40 bg-white"
              }`}
            >
              <div className="flex justify-between items-start">
                <span className="font-bold font-mono text-pine text-sm">{d.code}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-ink/5 border border-ink/10">
                  Рев. {d.revision}
                </span>
              </div>
              <p className="mt-1 font-medium text-ink">{d.title}</p>
              <div className="flex justify-between items-center mt-2 text-[10px] text-ink/50">
                <span>{d.current ? "✓ Действующий лист" : "Архивная ревизия"}</span>
                <span className="text-pine underline">Просмотр PDF →</span>
              </div>
            </div>
          ))}
        </div>

        {/* Architecture Specs block */}
        <div className="p-3 bg-stone-50 border border-ink/10 rounded-xl text-xs space-y-1.5">
          <p className="font-semibold text-ink text-[11px] uppercase tracking-wider">Параметры листа:</p>
          <div className="grid grid-cols-2 gap-1 text-[11px] text-ink/70">
            <div>Формат: <b>A3 Альбомный</b></div>
            <div>Масштаб: <b>1:100</b></div>
            <div>Стадия: <b>РП (Рабочий)</b></div>
            <div>Шрифт: <b>ГОСТ 2.304-81</b></div>
          </div>
        </div>
      </div>

      {/* Right Interactive PDF Viewer Viewport (8 cols) */}
      <div className="lg:col-span-8 flex flex-col bg-[#1A1F29] relative overflow-hidden">
        {/* PDF Controls Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 bg-[#12161F] text-paper border-b border-paper/10 text-xs z-10 select-none">
          {/* Navigation */}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={pageNum <= 1}
              onClick={() => setPageNum((p) => Math.max(1, p - 1))}
              className="px-2 py-1 bg-paper/10 hover:bg-paper/20 rounded disabled:opacity-30 transition-colors"
            >
              ◀ Назад
            </button>
            <span className="px-2 font-mono text-xs text-paper/80">
              Стр. {pageNum} из {totalPages}
            </span>
            <button
              type="button"
              disabled={pageNum >= totalPages}
              onClick={() => setPageNum((p) => Math.min(totalPages, p + 1))}
              className="px-2 py-1 bg-paper/10 hover:bg-paper/20 rounded disabled:opacity-30 transition-colors"
            >
              Вперед ▶
            </button>
          </div>

          {/* Zoom & View controls */}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setScale((s) => Math.max(0.4, Number((s - 0.2).toFixed(1))))}
              className="w-7 h-7 bg-paper/10 hover:bg-paper/20 rounded flex items-center justify-center font-bold"
              title="Уменьшить"
            >
              -
            </button>
            <span className="w-14 text-center font-mono text-xs">{Math.round(scale * 100)}%</span>
            <button
              type="button"
              onClick={() => setScale((s) => Math.min(3.0, Number((s + 0.2).toFixed(1))))}
              className="w-7 h-7 bg-paper/10 hover:bg-paper/20 rounded flex items-center justify-center font-bold"
              title="Увеличить"
            >
              +
            </button>
            <button
              type="button"
              onClick={handleFitWidth}
              className="px-2 py-1 bg-paper/10 hover:bg-paper/20 rounded text-[11px] transition-colors"
            >
              По ширине
            </button>
            <button
              type="button"
              onClick={() => setRotation((r) => (r + 90) % 360)}
              className="px-2 py-1 bg-paper/10 hover:bg-paper/20 rounded text-[11px] transition-colors"
              title="Повернуть на 90°"
            >
              ↻ 90°
            </button>
          </div>

          {/* Status badge */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-paper/50 font-mono">
              {customPdfName || `${selectedDrawing?.code || "АР-01"} · rev ${selectedDrawing?.revision || "A"}`}
            </span>
          </div>
        </div>

        {/* PDF Canvas Viewport Container */}
        <div
          ref={containerRef}
          className="flex-1 overflow-auto p-6 flex items-center justify-center relative min-h-[480px]"
        >
          {loading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#1A1F29]/80 z-20 text-paper space-y-2">
              <div className="w-8 h-8 border-2 border-pine border-t-transparent rounded-full animate-spin" />
              <p className="text-xs text-paper/70 font-mono">Рендеринг страницы через PDF.js...</p>
            </div>
          )}

          {error && (
            <div className="p-4 bg-clay/20 border border-clay/40 text-clay rounded-xl max-w-md text-center text-xs">
              <p className="font-bold mb-1">Ошибка отображения чертежа:</p>
              <p>{error}</p>
            </div>
          )}

          {/* HTML5 Canvas rendered by Mozilla PDF.js */}
          <div className="shadow-2xl border border-paper/10 rounded overflow-hidden bg-white">
            <canvas ref={canvasRef} className="block max-w-none" />
          </div>
        </div>

        {/* Bottom CAD status line */}
        <div className="px-4 py-1.5 bg-[#12161F] text-paper/50 text-[10px] flex justify-between items-center border-t border-paper/5">
          <span>Engine: Mozilla PDF.js v6 (Client-side Vector Renderer)</span>
          <span>Векторный CAD-просмотрщик строительных чертежей</span>
        </div>
      </div>
    </div>
  );
}
