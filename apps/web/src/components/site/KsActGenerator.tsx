"use client";

import { useEffect, useState, useRef } from "react";
import type { Locale } from "@/lib/types";
import { fetchActVat } from "@/lib/api";
import { bytesToBlob, saveBlobDownload, XLSX_MIME } from "@/lib/native";
import dynamic from "next/dynamic";

const SignaturePad = dynamic(
  () => import("./SignaturePad").then((m) => m.SignaturePad),
  {
    ssr: false,
    loading: () => (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs">
        <div className="bg-white rounded-2xl p-6 shadow-xl flex items-center gap-3">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-pine" />
          <span className="text-sm font-medium">Открываем модуль подписи...</span>
        </div>
      </div>
    ),
  }
);

// ─── Types ────────────────────────────────────────────────────────────────────
interface BudgetLine {
  id: string;
  code: string;
  title: string;
  budget_kzt: number;
  committed_kzt: number;
  actual_kzt: number;
}

interface KsWorkItem {
  id: string;
  num: string;
  name: string;
  unit: string;
  qty_contract: number;
  qty_period: number;
  price_kzt: number;
}

interface KsHeader {
  contractor: string;
  customer: string;
  object: string;
  contract_num: string;
  contract_date: string;
  report_start: string;
  report_end: string;
  act_num: string;
  ks3_num: string;
  act_date: string;
}

interface ActTax {
  percent: number;
  noVat: boolean;
  priorKzt: number;
  basis: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt(n: number) {
  return n.toLocaleString("ru-KZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function today() {
  return new Date().toISOString().split("T")[0];
}
function monthStart() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function taxAmount(base: number, tax: ActTax) {
  if (tax.noVat || tax.percent <= 0) return 0;
  return Math.round(base * (tax.percent / 100));
}

function vatRowLabel(tax: ActTax) {
  return tax.noVat ? "Без НДС" : `НДС ${tax.percent}%`;
}

function vatFootnote(tax: ActTax, actDate: string) {
  if (tax.noVat) return "НДС не начисляется: исполнитель не является плательщиком НДС.";
  return `Суммы в тенге (KZT). НДС ${tax.percent}% на дату акта ${actDate} согласно ${tax.basis}.`;
}

function priorNote(prev: number) {
  if (prev === 0) return "«Выполнено ранее» — сумма ранее подписанных актов. Подписанных актов нет, сумма 0.";
  return "«Выполнено ранее» — сумма ранее подписанных актов.";
}

function signCaption(signed?: string) {
  return signed ? "подпись" : "подпись / расшифровка";
}

// ─── Budget → work items converter ───────────────────────────────────────────
function budgetToItems(lines: BudgetLine[]): KsWorkItem[] {
  const units: Record<string, string> = {
    "01": "м³", "02": "м³", "03": "м²", "04": "компл.", "05": "компл.",
  };
  return lines.map((l, i) => ({
    id: l.id,
    num: String(i + 1),
    name: l.title,
    unit: units[l.code] ?? "компл.",
    qty_contract: 1,
    qty_period: l.actual_kzt > 0 ? 1 : 0,
    price_kzt: l.actual_kzt > 0 ? l.actual_kzt : l.committed_kzt,
  }));
}

// ─── KS-2 Print Template ──────────────────────────────────────────────────────
function printKs2(
  header: KsHeader,
  items: KsWorkItem[],
  locale: string,
  tax: ActTax,
  contractorSig?: string,
  customerSig?: string
) {
  const total = items.reduce((s, r) => s + r.qty_period * r.price_kzt, 0);
  const nds = taxAmount(total, tax);
  const withNds = total + nds;
  const vatLabel = vatRowLabel(tax);
  const grandLabel = tax.noVat ? "ИТОГО К ОПЛАТЕ (без НДС):" : "ИТОГО (с НДС):";

  const rows = items
    .map(
      (r, i) => `
      <tr>
        <td style="text-align:center">${i + 1}</td>
        <td>${r.name}</td>
        <td style="text-align:center">${r.unit}</td>
        <td style="text-align:right">${r.qty_contract}</td>
        <td style="text-align:right">${r.qty_period}</td>
        <td style="text-align:right">${fmt(r.price_kzt)}</td>
        <td style="text-align:right">${fmt(r.qty_period * r.price_kzt)}</td>
      </tr>`
    )
    .join("");

  const html = `<!DOCTYPE html>
<html lang="${locale}">
<head>
<meta charset="UTF-8"/>
<title>КС-2 · ${header.act_num}</title>
<style>
  @page { size: A4 landscape; margin: 15mm 12mm; }
  * { box-sizing: border-box; }
  body { font-family: "Times New Roman", serif; font-size: 10pt; color: #000; }
  h1 { font-size: 13pt; font-weight: bold; text-align: center; margin: 0 0 4px; }
  h2 { font-size: 11pt; font-weight: bold; text-align: center; margin: 0 0 10px; }
  .meta { width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 9.5pt; }
  .meta td { padding: 2px 4px; }
  .meta .label { width: 200px; font-weight: bold; }
  table.grid { width: 100%; border-collapse: collapse; margin-bottom: 8px; font-size: 9pt; }
  table.grid th, table.grid td { border: 1px solid #000; padding: 2px 4px; vertical-align: top; }
  table.grid th { background: #f0f0f0; text-align: center; font-weight: bold; }
  .total-row td { font-weight: bold; background: #f8f8f8; }
  .sign { margin-top: 24px; display: flex; justify-content: space-between; font-size: 9.5pt; }
  .sign-block { width: 45%; }
  .sign-line { border-bottom: 1px solid #000; margin: 20px 0 4px; }
  .footnote { font-size: 8pt; color: #555; margin-top: 6px; }
  @media print { .no-print { display: none; } }
</style>
</head>
<body>
  <h1>УНИФИЦИРОВАННАЯ ФОРМА КС-2</h1>
  <h2>АКТ О ПРИЁМКЕ ВЫПОЛНЕННЫХ РАБОТ</h2>

  <table class="meta">
    <tr><td class="label">Организация-подрядчик:</td><td>${header.contractor}</td><td class="label">Акт №:</td><td>${header.act_num}</td></tr>
    <tr><td class="label">Заказчик:</td><td>${header.customer}</td><td class="label">Дата составления:</td><td>${header.act_date}</td></tr>
    <tr><td class="label">Объект строительства:</td><td>${header.object}</td><td class="label">Отчётный период:</td><td>${header.report_start} — ${header.report_end}</td></tr>
    <tr><td class="label">Договор подряда №:</td><td>${header.contract_num}</td><td class="label">Дата договора:</td><td>${header.contract_date}</td></tr>
  </table>

  <table class="grid">
    <thead>
      <tr>
        <th rowspan="2" style="width:32px">№</th>
        <th rowspan="2">Наименование работ</th>
        <th rowspan="2">Ед. изм.</th>
        <th colspan="2">Количество</th>
        <th rowspan="2">Цена за ед. (тг)</th>
        <th rowspan="2">Стоимость (тг)</th>
      </tr>
      <tr>
        <th>по договору</th>
        <th>в отч. пер.</th>
      </tr>
    </thead>
    <tbody>
      ${rows}
      <tr class="total-row">
        <td colspan="6" style="text-align:right">ИТОГО (без НДС):</td>
        <td style="text-align:right">${fmt(total)}</td>
      </tr>
      <tr class="total-row">
        <td colspan="6" style="text-align:right">${vatLabel}:</td>
        <td style="text-align:right">${fmt(nds)}</td>
      </tr>
      <tr class="total-row">
        <td colspan="6" style="text-align:right">${grandLabel}</td>
        <td style="text-align:right">${fmt(withNds)}</td>
      </tr>
    </tbody>
  </table>

  <p class="footnote">${vatFootnote(tax, header.act_date)}</p>

  <div class="sign">
    <div class="sign-block">
      <p><b>Сдал:</b> Подрядчик (${header.contractor})</p>
      <div style="height: 48px; display: flex; align-items: flex-end; border-bottom: 1px solid #000; margin: 12px 0 4px;">
        ${
          contractorSig
            ? `<img src="${contractorSig}" style="max-height: 45px; max-width: 160px; object-fit: contain; margin-bottom: 2px;" alt="Подпись подрядчика" />`
            : ""
        }
      </div>
      <p>__________________ / ________________</p>
      <p style="font-size:8pt; color: #555;">${signCaption(contractorSig)}</p>
    </div>
    <div class="sign-block">
      <p><b>Принял:</b> Заказчик (${header.customer})</p>
      <div style="height: 48px; display: flex; align-items: flex-end; border-bottom: 1px solid #000; margin: 12px 0 4px;">
        ${
          customerSig
            ? `<img src="${customerSig}" style="max-height: 45px; max-width: 160px; object-fit: contain; margin-bottom: 2px;" alt="Подпись заказчика" />`
            : ""
        }
      </div>
      <p>__________________ / ________________</p>
      <p style="font-size:8pt; color: #555;">${signCaption(customerSig)}</p>
    </div>
  </div>
</body>
</html>`;
  return { html, total, nds, withNds };
}

function printKs3(
  header: KsHeader,
  items: KsWorkItem[],
  locale: string,
  tax: ActTax,
  contractorSig?: string,
  customerSig?: string
) {
  const cur = items.reduce((s, r) => s + r.qty_period * r.price_kzt, 0);
  const prev = tax.priorKzt;
  const fromStart = cur + prev;
  const nds = taxAmount(cur, tax);
  const withNds = cur + nds;
  const vatLabel = vatRowLabel(tax);
  const grandLabel = tax.noVat ? "ИТОГО К ОПЛАТЕ (без НДС):" : "ИТОГО С НДС (к оплате):";

  const html = `<!DOCTYPE html>
<html lang="${locale}">
<head>
<meta charset="UTF-8"/>
<title>КС-3 · ${header.ks3_num}</title>
<style>
  @page { size: A4; margin: 15mm 12mm; }
  * { box-sizing: border-box; }
  body { font-family: "Times New Roman", serif; font-size: 10pt; color: #000; }
  h1 { font-size: 13pt; font-weight: bold; text-align: center; margin: 0 0 4px; }
  h2 { font-size: 11pt; font-weight: bold; text-align: center; margin: 0 0 10px; }
  .meta { width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 9.5pt; }
  .meta td { padding: 2px 4px; }
  .meta .label { width: 220px; font-weight: bold; }
  table.grid { width: 100%; border-collapse: collapse; margin-bottom: 8px; font-size: 9.5pt; }
  table.grid th, table.grid td { border: 1px solid #000; padding: 3px 6px; }
  table.grid th { background: #f0f0f0; text-align: center; font-weight: bold; }
  .total-row td { font-weight: bold; }
  .grand td { font-weight: bold; font-size: 11pt; background: #f8f8f8; }
  .sign { margin-top: 30px; display: flex; justify-content: space-between; font-size: 9.5pt; }
  .sign-block { width: 45%; }
  .sign-line { border-bottom: 1px solid #000; margin: 12px 0 4px; height: 48px; display: flex; align-items: flex-end; }
  @media print { .no-print { display: none; } }
</style>
</head>
<body>
  <h1>УНИФИЦИРОВАННАЯ ФОРМА КС-3</h1>
  <h2>СПРАВКА О СТОИМОСТИ ВЫПОЛНЕННЫХ РАБОТ И ЗАТРАТ</h2>

  <table class="meta">
    <tr><td class="label">Организация-подрядчик:</td><td>${header.contractor}</td><td class="label">Справка №:</td><td>${header.ks3_num}</td></tr>
    <tr><td class="label">Заказчик:</td><td>${header.customer}</td><td class="label">Дата:</td><td>${header.act_date}</td></tr>
    <tr><td class="label">Объект строительства:</td><td>${header.object}</td><td class="label">Отчётный период:</td><td>${header.report_start} — ${header.report_end}</td></tr>
    <tr><td class="label">Договор подряда №:</td><td>${header.contract_num}</td><td class="label">от:</td><td>${header.contract_date}</td></tr>
  </table>

  <table class="grid">
    <thead>
      <tr>
        <th style="width:32px">№</th>
        <th>Наименование пускового комплекса, этапа</th>
        <th style="width:140px">С начала строительства (тг)</th>
        <th style="width:140px">С начала года (тг)</th>
        <th style="width:140px">В т.ч. за отч. период (тг)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="text-align:center">1</td>
        <td>${header.object}</td>
        <td style="text-align:right">${fmt(fromStart)}</td>
        <td style="text-align:right">—</td>
        <td style="text-align:right">${fmt(cur)}</td>
      </tr>
      <tr>
        <td style="text-align:center">2</td>
        <td>Выполнено ранее</td>
        <td style="text-align:right">${fmt(prev)}</td>
        <td style="text-align:right">—</td>
        <td style="text-align:right">—</td>
      </tr>
      <tr class="total-row">
        <td colspan="4" style="text-align:right">Итого выполнено работ (без НДС):</td>
        <td style="text-align:right">${fmt(cur)}</td>
      </tr>
      <tr class="total-row">
        <td colspan="4" style="text-align:right">${vatLabel}:</td>
        <td style="text-align:right">${fmt(nds)}</td>
      </tr>
      <tr class="grand">
        <td colspan="4" style="text-align:right">${grandLabel}</td>
        <td style="text-align:right">${fmt(withNds)}</td>
      </tr>
    </tbody>
  </table>

  <p style="font-size:8pt; color:#555; margin-top:6px;">${priorNote(prev)} ${vatFootnote(tax, header.act_date)} С начала года отдельно не считается: такой разбивки в подписанных актах нет.</p>

  <div class="sign">
    <div class="sign-block">
      <p><b>Подрядчик:</b> ${header.contractor}</p>
      <div class="sign-line">
        ${
          contractorSig
            ? `<img src="${contractorSig}" style="max-height: 45px; max-width: 160px; object-fit: contain; margin-bottom: 2px;" alt="Подпись подрядчика" />`
            : ""
        }
      </div>
      <p>__________________ / ________________</p>
      <p style="font-size:8pt; color: #555;">${signCaption(contractorSig)}</p>
    </div>
    <div class="sign-block">
      <p><b>Заказчик:</b> ${header.customer}</p>
      <div class="sign-line">
        ${
          customerSig
            ? `<img src="${customerSig}" style="max-height: 45px; max-width: 160px; object-fit: contain; margin-bottom: 2px;" alt="Подпись заказчика" />`
            : ""
        }
      </div>
      <p>__________________ / ________________</p>
      <p style="font-size:8pt; color: #555;">${signCaption(customerSig)}</p>
    </div>
  </div>
</body>
</html>`;
  return { html, cur, prev, total: fromStart, nds, withNds };
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function KsActGenerator({
  locale,
  projectId,
  projectTitle,
  projectAddress,
  budget,
}: {
  locale: Locale;
  projectId: string;
  projectTitle: string;
  projectAddress: string;
  budget: BudgetLine[];
}) {
  const isKk = locale === "kk";

  const [header, setHeader] = useState<KsHeader>({
    contractor: "ТОО Qurylys Group",
    customer: "Заказчик / Физическое лицо",
    object: projectTitle,
    contract_num: "ГП-2026/01",
    contract_date: "2026-09-01",
    report_start: monthStart(),
    report_end: today(),
    act_num: "КС-2/01",
    ks3_num: "КС-3/01",
    act_date: today(),
  });

  const [items, setItems] = useState<KsWorkItem[]>(() => budgetToItems(budget));
  const [previewMode, setPreviewMode] = useState<"ks2" | "ks3" | null>(null);
  const [previewHtml, setPreviewHtml] = useState("");
  const [totals, setTotals] = useState({ total: 0, nds: 0, withNds: 0 });
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Signatures
  const [showSignModal, setShowSignModal] = useState(false);
  const [contractorSig, setContractorSig] = useState<string>("");
  const [customerSig, setCustomerSig] = useState<string>("");

  // Loading states
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [isExportingExcel, setIsExportingExcel] = useState(false);
  const [noVat, setNoVat] = useState(false);
  const [tax, setTax] = useState<ActTax | null>(null);

  useEffect(() => {
    if (!header.act_date) {
      setTax(null);
      return;
    }
    let cancelled = false;
    fetchActVat(header.act_date, noVat, projectId)
      .then((row) => {
        if (cancelled) return;
        setTax({
          percent: row.vat_percent,
          noVat: row.no_vat,
          priorKzt: row.prior_signed_kzt,
          basis: row.basis || "НК РК № 214-VIII, ст. 503",
        });
      })
      .catch(() => {
        if (!cancelled) setTax(null);
      });
    return () => {
      cancelled = true;
    };
  }, [header.act_date, noVat, projectId]);

  function updateItem(id: string, field: keyof KsWorkItem, val: string | number) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, [field]: val } : it)));
  }

  function addItem() {
    setItems((prev) => [
      ...prev,
      {
        id: `item-${Date.now()}`,
        num: String(prev.length + 1),
        name: "Новая работа",
        unit: "компл.",
        qty_contract: 1,
        qty_period: 1,
        price_kzt: 0,
      },
    ]);
  }

  function removeItem(id: string) {
    setItems((prev) => prev.filter((it) => it.id !== id));
  }

  function openPreview(type: "ks2" | "ks3") {
    if (!tax) {
      alert("Ставка НДС ещё не получена с сервера");
      return;
    }
    if (type === "ks2") {
      const result = printKs2(header, items, locale, tax, contractorSig, customerSig);
      setPreviewHtml(result.html);
      setTotals({ total: result.total, nds: result.nds, withNds: result.withNds });
    } else {
      const result = printKs3(header, items, locale, tax, contractorSig, customerSig);
      setPreviewHtml(result.html);
      setTotals({ total: result.cur, nds: result.nds, withNds: result.withNds });
    }
    setPreviewMode(type);
  }

  function doPrint() {
    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(previewHtml);
    win.document.close();
    setTimeout(() => win.print(), 600);
  }

  // 1-Click Direct PDF Export using jsPDF + html2canvas
  async function downloadDirectPdf(type: "ks2" | "ks3") {
    if (!tax) {
      alert("Ставка НДС ещё не получена с сервера");
      return;
    }
    setIsGeneratingPdf(true);
    try {
      const html2canvas = (await import("html2canvas")).default;
      const { jsPDF } = await import("jspdf");

      const tempContainer = document.createElement("div");
      tempContainer.style.position = "fixed";
      tempContainer.style.left = "-9999px";
      tempContainer.style.top = "0";
      tempContainer.style.width = type === "ks2" ? "1100px" : "800px";
      tempContainer.style.background = "#ffffff";
      tempContainer.style.padding = "24px";

      const { html } =
        type === "ks2"
          ? printKs2(header, items, locale, tax, contractorSig, customerSig)
          : printKs3(header, items, locale, tax, contractorSig, customerSig);

      tempContainer.innerHTML = html;
      document.body.appendChild(tempContainer);

      const canvas = await html2canvas(tempContainer, {
        scale: 2,
        useCORS: true,
        logging: false,
      });

      document.body.removeChild(tempContainer);

      const imgData = canvas.toDataURL("image/png");
      const orientation = type === "ks2" ? "landscape" : "portrait";
      const pdf = new jsPDF({
        orientation,
        unit: "mm",
        format: "a4",
      });

      const pageWidth = orientation === "landscape" ? 297 : 210;
      const pageHeight = orientation === "landscape" ? 210 : 297;
      const imgWidth = pageWidth - 16;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;

      pdf.addImage(imgData, "PNG", 8, 8, imgWidth, Math.min(imgHeight, pageHeight - 16));
      const filename = `${type === "ks2" ? "KS-2" : "KS-3"}_${(type === "ks2" ? header.act_num : header.ks3_num).replace(/[/\\?%*:|"<>]/g, "-")}.pdf`;
      if (!(await saveBlobDownload(filename, pdf.output("blob")))) pdf.save(filename);
    } catch (err: any) {
      console.error("PDF generation failed:", err);
      alert("Ошибка экспорта PDF: " + err.message);
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  // Export to Excel (.xlsx) using xlsx library
  async function exportToExcel() {
    if (!tax) {
      alert("Ставка НДС ещё не получена с сервера");
      return;
    }
    setIsExportingExcel(true);
    try {
      const XLSX = await import("xlsx");
      const wb = XLSX.utils.book_new();

      const total = items.reduce((s, r) => s + r.qty_period * r.price_kzt, 0);
      const nds = taxAmount(total, tax);
      const withNds = total + nds;

      const data = [
        ["УНИФИЦИРОВАННАЯ ФОРМА КС-2"],
        ["АКТ О ПРИЁМКЕ ВЫПОЛНЕННЫХ РАБОТ №", header.act_num, "от", header.act_date],
        [],
        ["Подрядчик:", header.contractor],
        ["Заказчик:", header.customer],
        ["Объект строительства:", header.object],
        ["Договор подряда №:", header.contract_num, "от", header.contract_date],
        ["Отчетный период:", `${header.report_start} — ${header.report_end}`],
        [],
        [
          "№",
          "Наименование работ и затрат",
          "Ед. изм.",
          "Кол-во по договору",
          "Кол-во за отчетный период",
          "Цена за ед. (тенге)",
          "Стоимость выполненных работ (тенге)",
        ],
        ...items.map((it, idx) => [
          idx + 1,
          it.name,
          it.unit,
          it.qty_contract,
          it.qty_period,
          it.price_kzt,
          it.qty_period * it.price_kzt,
        ]),
        [],
        ["", "", "", "", "", "ИТОГО (без НДС):", total],
        ["", "", "", "", "", `${vatRowLabel(tax)}:`, nds],
        ["", "", "", "", "", tax.noVat ? "ВСЕГО К ОПЛАТЕ (без НДС):" : "ВСЕГО К ОПЛАТЕ (с НДС):", withNds],
        ["", "", "", "", "", "Выполнено ранее:", tax.priorKzt],
        [],
        ["Сдал (Подрядчик):", header.contractor, "", "", "Принял (Заказчик):", header.customer],
        [
          contractorSig ? "подпись" : "Подпись: ________________________",
          "",
          "",
          "",
          customerSig ? "подпись" : "Подпись: ________________________",
        ],
        [priorNote(tax.priorKzt)],
        [vatFootnote(tax, header.act_date)],
      ];

      const ws = XLSX.utils.aoa_to_sheet(data);
      ws["!cols"] = [
        { wch: 6 },
        { wch: 38 },
        { wch: 10 },
        { wch: 18 },
        { wch: 22 },
        { wch: 18 },
        { wch: 24 },
      ];

      XLSX.utils.book_append_sheet(wb, ws, "КС-2 Акт");
      const filename = `KS-2_${header.act_num.replace(/[/\\?%*:|"<>]/g, "-")}.xlsx`;
      const saved = await saveBlobDownload(filename, bytesToBlob(XLSX.write(wb, { bookType: "xlsx", type: "array" }), XLSX_MIME));
      if (!saved) XLSX.writeFile(wb, filename);
    } catch (err: any) {
      console.error("Excel export error:", err);
      alert("Ошибка экспорта Excel: " + err.message);
    } finally {
      setIsExportingExcel(false);
    }
  }

  const grandTotal = items.reduce((s, r) => s + r.qty_period * r.price_kzt, 0);
  const nds = tax ? taxAmount(grandTotal, tax) : 0;
  const payableLabel = tax?.noVat ? "К оплате (без НДС)" : "К оплате (с НДС)";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white rounded-xl border border-ink/10 p-4 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-serif text-lg font-bold text-ink">
                {isKk ? "КС-2 / КС-3 актілер генераторы" : "📄 Генератор актов КС-2 / КС-3"}
              </h3>
              <span className="text-[10px] bg-emerald-100 text-emerald-800 font-semibold px-2 py-0.5 rounded-full">
                PDF + Excel + подпись
              </span>
            </div>
            <p className="text-xs text-ink/50 mt-0.5">
              {isKk
                ? "Қол қою, PDF басып шығару және Excel-ге экспорттау"
                : "Подпись на экране · Экспорт в Excel (.xlsx) · Прямой PDF"}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Signature Button */}
            <button
              type="button"
              onClick={() => setShowSignModal(true)}
              className="px-3 py-2 bg-amber-50 border border-amber-300 text-amber-900 text-xs font-semibold rounded-xl hover:bg-amber-100 transition-colors flex items-center gap-1.5 shadow-xs"
            >
              <span>✍️</span>
              <span>
                {contractorSig && customerSig
                  ? "Подписано обеими сторонами ✓"
                  : contractorSig || customerSig
                  ? "Частично подписано (1/2)"
                  : "Подпись"}
              </span>
            </button>

            {/* Excel Export Button */}
            <button
              type="button"
              disabled={isExportingExcel}
              onClick={exportToExcel}
              className="px-3 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-xl hover:bg-emerald-700 transition-colors flex items-center gap-1.5 shadow-xs disabled:opacity-50"
            >
              <span>📊</span>
              <span>{isExportingExcel ? "Экспорт..." : "В Excel (.xlsx)"}</span>
            </button>

            {/* Direct PDF Download Button */}
            <button
              type="button"
              disabled={isGeneratingPdf}
              onClick={() => downloadDirectPdf("ks2")}
              className="px-3.5 py-2 bg-slate-800 text-white text-xs font-semibold rounded-xl hover:bg-slate-900 transition-colors flex items-center gap-1.5 shadow-xs disabled:opacity-50"
            >
              <span>📥</span>
              <span>{isGeneratingPdf ? "Генерация..." : "Скачать PDF (jsPDF)"}</span>
            </button>

            {/* View KS-2 preview */}
            <button
              type="button"
              onClick={() => openPreview("ks2")}
              className="px-3.5 py-2 bg-pine text-white text-xs font-semibold rounded-xl hover:bg-pine/90 shadow-xs"
            >
              Форма КС-2
            </button>

            {/* View KS-3 preview */}
            <button
              type="button"
              onClick={() => openPreview("ks3")}
              className="px-3.5 py-2 bg-stone-700 text-white text-xs font-semibold rounded-xl hover:bg-stone-800 shadow-xs"
            >
              Форма КС-3
            </button>
          </div>
        </div>

        {/* Signature Status Badges */}
        <div className="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-ink/10 text-xs">
          <span className="text-ink/45 text-[11px] uppercase font-semibold">Статус подписания:</span>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${contractorSig ? "bg-emerald-500" : "bg-ink/30"}`}
            />
            <span className={contractorSig ? "text-emerald-700 font-medium" : "text-ink/60"}>
              Подрядчик ({header.contractor}): {contractorSig ? "Подписано ✓" : "Ожидает подписи"}
            </span>
          </div>
          <span className="text-ink/20">|</span>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${customerSig ? "bg-emerald-500" : "bg-ink/30"}`}
            />
            <span className={customerSig ? "text-emerald-700 font-medium" : "text-ink/60"}>
              Заказчик ({header.customer}): {customerSig ? "Подписано ✓" : "Ожидает подписи"}
            </span>
          </div>
        </div>
      </div>

      {/* Totals summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white border border-ink/10 rounded-xl p-3">
          <p className="text-[10px] text-ink/45 uppercase tracking-wider">Итого (без НДС)</p>
          <p className="text-xl font-bold text-ink mt-0.5">{grandTotal.toLocaleString()} ₸</p>
        </div>
        <div className="bg-white border border-ink/10 rounded-xl p-3">
          <p className="text-[10px] text-ink/45 uppercase tracking-wider">{tax ? vatRowLabel(tax) : "НДС"}</p>
          <p className="text-xl font-bold text-amber-600 mt-0.5">{tax ? `${nds.toLocaleString()} ₸` : "…"}</p>
        </div>
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3">
          <p className="text-[10px] text-emerald-600 uppercase tracking-wider font-semibold">{payableLabel}</p>
          <p className="text-xl font-bold text-emerald-800 mt-0.5">{(grandTotal + nds).toLocaleString()} ₸</p>
        </div>
      </div>

      {/* Header form */}
      <div className="bg-white border border-ink/10 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-ink/10 bg-paper/50">
          <p className="text-xs font-semibold text-ink/60 uppercase tracking-wider">Реквизиты документа</p>
        </div>
        <div className="p-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
          {(
            [
              ["contractor", "Подрядчик"],
              ["customer", "Заказчик"],
              ["object", "Объект строительства"],
              ["contract_num", "Договор №"],
              ["contract_date", "Дата договора"],
              ["report_start", "Начало периода"],
              ["report_end", "Конец периода"],
              ["act_num", "Номер КС-2"],
              ["ks3_num", "Номер КС-3"],
              ["act_date", "Дата акта"],
            ] as [keyof KsHeader, string][]
          ).map(([field, label]) => (
            <div key={field}>
              <label className="block text-[10px] text-ink/50 uppercase tracking-wider mb-1">{label}</label>
              <input
                type={field.includes("date") || field.includes("start") || field.includes("end") ? "date" : "text"}
                value={header[field]}
                onChange={(e) => setHeader((h) => ({ ...h, [field]: e.target.value }))}
                className="w-full border border-ink/15 rounded-lg px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-pine/40"
              />
            </div>
          ))}
          <label className="flex items-end gap-2 text-sm pb-1">
            <input
              type="checkbox"
              checked={noVat}
              onChange={(e) => setNoVat(e.target.checked)}
              className="mb-1"
            />
            <span>
              <span className="block text-[10px] text-ink/50 uppercase tracking-wider">Режим НДС</span>
              без НДС
            </span>
          </label>
        </div>
        <p className="px-4 pb-3 text-[11px] text-ink/50">
          {tax
            ? `${vatFootnote(tax, header.act_date)} ${priorNote(tax.priorKzt)}`
            : "Ставка НДС загружается с сервера по дате акта."}
        </p>
      </div>

      {/* Work items table */}
      <div className="bg-white border border-ink/10 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink/10 bg-paper/50">
          <p className="text-xs font-semibold text-ink/60 uppercase tracking-wider">Работы и затраты (строки КС-2)</p>
          <button
            type="button"
            onClick={addItem}
            className="px-3 py-1.5 bg-pine text-white text-xs font-semibold rounded-lg hover:bg-pine/90 shadow-xs"
          >
            + Добавить строку
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-ink/5">
                <th className="border-b border-ink/10 px-3 py-2 text-left font-semibold text-ink/60 w-8">№</th>
                <th className="border-b border-ink/10 px-3 py-2 text-left font-semibold text-ink/60">Наименование работ</th>
                <th className="border-b border-ink/10 px-3 py-2 text-center font-semibold text-ink/60 w-20">Ед. изм.</th>
                <th className="border-b border-ink/10 px-3 py-2 text-right font-semibold text-ink/60 w-24">Кол-во (дог.)</th>
                <th className="border-b border-ink/10 px-3 py-2 text-right font-semibold text-ink/60 w-24">Кол-во (пер.)</th>
                <th className="border-b border-ink/10 px-3 py-2 text-right font-semibold text-ink/60 w-32">Цена (₸)</th>
                <th className="border-b border-ink/10 px-3 py-2 text-right font-semibold text-ink/60 w-32">Сумма (₸)</th>
                <th className="border-b border-ink/10 px-3 py-2 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr key={item.id} className="border-b border-ink/8 hover:bg-ink/2">
                  <td className="px-3 py-1.5 text-ink/50 text-center">{idx + 1}</td>
                  <td className="px-3 py-1.5">
                    <input
                      value={item.name}
                      onChange={(e) => updateItem(item.id, "name", e.target.value)}
                      className="w-full border-0 bg-transparent focus:outline-none focus:ring-1 focus:ring-pine/30 rounded px-1"
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      value={item.unit}
                      onChange={(e) => updateItem(item.id, "unit", e.target.value)}
                      className="w-full border-0 bg-transparent text-center focus:outline-none focus:ring-1 focus:ring-pine/30 rounded px-1"
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      type="number"
                      value={item.qty_contract}
                      onChange={(e) => updateItem(item.id, "qty_contract", Number(e.target.value))}
                      className="w-full border-0 bg-transparent text-right focus:outline-none focus:ring-1 focus:ring-pine/30 rounded px-1"
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      type="number"
                      value={item.qty_period}
                      onChange={(e) => updateItem(item.id, "qty_period", Number(e.target.value))}
                      className="w-full border-0 bg-transparent text-right focus:outline-none focus:ring-1 focus:ring-pine/30 rounded px-1"
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      type="number"
                      value={item.price_kzt}
                      onChange={(e) => updateItem(item.id, "price_kzt", Number(e.target.value))}
                      className="w-full border-0 bg-transparent text-right font-mono focus:outline-none focus:ring-1 focus:ring-pine/30 rounded px-1"
                    />
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono font-semibold text-ink">
                    {(item.qty_period * item.price_kzt).toLocaleString()}
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <button
                      type="button"
                      onClick={() => removeItem(item.id)}
                      className="text-clay/60 hover:text-clay text-xs"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
              {/* Totals */}
              <tr className="bg-ink/5 font-semibold">
                <td colSpan={6} className="px-3 py-2 text-right text-xs">ИТОГО (без НДС):</td>
                <td className="px-3 py-2 text-right font-mono">{grandTotal.toLocaleString()}</td>
                <td />
              </tr>
              <tr className="bg-amber-50 font-semibold">
                <td colSpan={6} className="px-3 py-2 text-right text-xs text-amber-700">{tax ? `${vatRowLabel(tax)}:` : "НДС:"}</td>
                <td className="px-3 py-2 text-right font-mono text-amber-700">{nds.toLocaleString()}</td>
                <td />
              </tr>
              <tr className="bg-emerald-50 font-bold">
                <td colSpan={6} className="px-3 py-2 text-right text-xs text-emerald-800">{tax?.noVat ? "ИТОГО (без НДС):" : "ИТОГО (с НДС):"}</td>
                <td className="px-3 py-2 text-right font-mono text-emerald-800">{(grandTotal + nds).toLocaleString()}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Feature Capabilities Info Box */}
      <div className="grid sm:grid-cols-3 gap-3 text-xs">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-amber-800">
          <p className="font-semibold mb-1">✍️ React Signature Canvas</p>
          <p className="text-amber-700 text-[11px]">
            Подписание акта на сенсорном экране или мышью с сохранением цифрового слепка подписи.
          </p>
        </div>
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-emerald-800">
          <p className="font-semibold mb-1">📊 ExcelJS / XLSX Экспорт</p>
          <p className="text-emerald-700 text-[11px]">
            Мгновенная выгрузка полноценной сметы в .xlsx файл для бухгалтерии и 1С.
          </p>
        </div>
        <div className="bg-sky-50 border border-sky-200 rounded-xl p-3 text-sky-800">
          <p className="font-semibold mb-1">🖨 jsPDF + html2canvas</p>
          <p className="text-sky-700 text-[11px]">
            Прямое скачивание готового PDF без открытия системного окна печати браузера.
          </p>
        </div>
      </div>

      {/* Signature Pad Modal */}
      {showSignModal && (
        <SignaturePad
          contractorName={header.contractor}
          customerName={header.customer}
          initialContractor={contractorSig}
          initialCustomer={customerSig}
          onSave={(c, k) => {
            setContractorSig(c);
            setCustomerSig(k);
          }}
          onClose={() => setShowSignModal(false)}
        />
      )}

      {/* Preview Modal */}
      {previewMode && (
        <div className="fixed inset-0 z-50 bg-ink/50 backdrop-blur-xs flex flex-col">
          <div className="flex items-center justify-between bg-white px-6 py-3 border-b border-ink/10 shadow-xs">
            <div>
              <h3 className="font-semibold text-ink">
                Предпросмотр · {previewMode === "ks2" ? "КС-2 (Акт выполненных работ)" : "КС-3 (Справка о стоимости)"}
              </h3>
              <p className="text-xs text-ink/50 mt-0.5">
                Итого с НДС: <span className="font-bold text-emerald-700">{totals.withNds.toLocaleString()} ₸</span>
                {contractorSig && customerSig && " · Обе стороны подписали ✓"}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => downloadDirectPdf(previewMode)}
                className="px-3.5 py-1.5 bg-slate-800 text-white text-xs font-semibold rounded-lg hover:bg-slate-900 shadow-xs"
              >
                📥 Скачать PDF
              </button>
              <button
                type="button"
                onClick={doPrint}
                className="px-3.5 py-1.5 bg-pine text-white text-xs font-semibold rounded-lg hover:bg-pine/90 shadow-xs"
              >
                🖨 Печать браузера
              </button>
              <button
                type="button"
                onClick={() => setPreviewMode(null)}
                className="px-3.5 py-1.5 border border-ink/15 text-xs rounded-lg hover:bg-ink/5"
              >
                Закрыть
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-hidden">
            <iframe
              ref={iframeRef}
              srcDoc={previewHtml}
              className="w-full h-full border-0 bg-white"
              title="КС предпросмотр"
            />
          </div>
        </div>
      )}
    </div>
  );
}
