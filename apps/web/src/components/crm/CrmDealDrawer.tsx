"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import {
  createActivity,
  createInvoice,
  dealToProject,
  fetchDealDetail,
  moveDeal,
  payInvoice,
  toggleActivity,
} from "@/lib/api";
import { ACTIVITY_TYPE, FUNNEL, INVOICE_STATUS, STAGE, money } from "@/lib/format";
import type { CrmActivity, CrmInvoice, Deal, Locale } from "@/lib/types";
import { t } from "@/i18n/messages";

export function CrmDealDrawer({
  deal,
  stages,
  locale,
  onClose,
  onDealUpdated,
}: {
  deal: Deal;
  stages: Record<string, string[]>;
  locale: Locale;
  onClose: () => void;
  onDealUpdated: () => void;
}) {
  const m = t(locale);
  const { user } = useAuth();
  const [currentDeal, setCurrentDeal] = useState<Deal>(deal);
  const [activities, setActivities] = useState<CrmActivity[]>([]);
  const [invoices, setInvoices] = useState<CrmInvoice[]>([]);
  const [loading, setLoading] = useState(true);

  // Composer state
  const [composerTab, setComposerTab] = useState<"note" | "call" | "site_visit" | "task" | "invoice">("note");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [invoiceAmount, setInvoiceAmount] = useState(deal.amount_kzt || 0);
  const [invoicePayer, setInvoicePayer] = useState(deal.client_name || "");
  const [invoiceIin, setInvoiceIin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [projectCreated, setProjectCreated] = useState<string | null>(deal.project_id || null);

  function loadDetails() {
    if (!user) return;
    setLoading(true);
    fetchDealDetail(user.email, currentDeal.id)
      .then((res) => {
        setCurrentDeal(res.deal);
        setActivities(res.activities || []);
        setInvoices(res.invoices || []);
        if (res.deal.project_id) setProjectCreated(res.deal.project_id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadDetails();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDeal.id, user]);

  async function handleMoveStage(newStage: string) {
    if (!user || newStage === currentDeal.stage) return;
    try {
      const updated = await moveDeal(user.email, currentDeal.id, newStage);
      setCurrentDeal(updated);
      loadDetails();
      onDealUpdated();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function handleToggleActivity(actId: string, currentCompleted: boolean) {
    if (!user) return;
    try {
      await toggleActivity(user.email, actId, !currentCompleted);
      loadDetails();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function handlePayInvoice(invId: string) {
    if (!user) return;
    try {
      await payInvoice(user.email, invId);
      loadDetails();
      onDealUpdated();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function handleConvertToProject() {
    if (!user) return;
    try {
      const res = await dealToProject(user.email, currentDeal.id);
      setProjectCreated(String(res.id));
      loadDetails();
      onDealUpdated();
      alert("Строительный проект успешно сформирован в ProjectHub!");
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function handleComposerSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setSubmitting(true);

    try {
      if (composerTab === "invoice") {
        if (!title.trim()) {
          alert("Укажите назначение счета");
          setSubmitting(false);
          return;
        }
        await createInvoice(user.email, {
          deal_id: currentDeal.id,
          title: title.trim(),
          amount_kzt: Number(invoiceAmount),
          payer_name: invoicePayer.trim() || currentDeal.client_name || "Клиент",
          payer_iin_bin: invoiceIin.trim(),
          escrow_enabled: true,
          due_date: dueDate || new Date().toISOString().slice(0, 10),
        });
      } else {
        if (!title.trim()) {
          alert("Укажите заголовок");
          setSubmitting(false);
          return;
        }
        await createActivity(user.email, {
          deal_id: currentDeal.id,
          activity_type: composerTab,
          title: title.trim(),
          description: description.trim(),
          due_date: dueDate,
        });
      }

      setTitle("");
      setDescription("");
      setDueDate("");
      loadDetails();
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const currentFunnelStages = stages[currentDeal.funnel] ?? [];
  const currentStageIdx = currentFunnelStages.indexOf(currentDeal.stage);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/40 backdrop-blur-xs animate-fadeIn">
      <div
        className="w-full max-w-4xl bg-white shadow-2xl h-full flex flex-col overflow-hidden border-l border-ink/15"
        role="dialog"
      >
        {/* Top Header Bar */}
        <div className="px-6 py-4 border-b border-ink/10 flex items-center justify-between bg-pine/5">
          <div>
            <div className="flex items-center gap-2 text-xs text-ink/60 mb-1">
              <span className="font-semibold uppercase tracking-wider text-pine">
                {FUNNEL[currentDeal.funnel]?.[locale] ?? currentDeal.funnel}
              </span>
              <span>•</span>
              <span className="font-mono text-ink/45">#{currentDeal.id}</span>
            </div>
            <h2 className="text-xl font-serif font-bold text-ink">{currentDeal.title}</h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-lg font-bold text-pine font-mono">{money(currentDeal.amount_kzt, locale)}</span>
            <button
              type="button"
              onClick={onClose}
              className="grid place-items-center h-8 w-8 rounded-full border border-ink/15 hover:bg-ink/5 text-ink/70"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Bitrix24 Stage Stepper */}
        <div className="px-6 py-2.5 bg-paper border-b border-ink/10 overflow-x-auto">
          <p className="text-[11px] uppercase tracking-wider text-ink/45 mb-1.5 font-medium">Стадия сделки (клик для перехода):</p>
          <div className="flex items-center gap-1.5 min-w-max">
            {currentFunnelStages.map((st, i) => {
              const isPast = currentStageIdx >= 0 && i <= currentStageIdx;
              const isCurrent = i === currentStageIdx;
              const meta = STAGE[st];
              return (
                <button
                  key={st}
                  type="button"
                  onClick={() => handleMoveStage(st)}
                  className={`px-3 py-1 text-xs rounded-md border font-medium transition-all ${
                    isCurrent
                      ? "bg-pine text-white border-pine shadow-sm ring-2 ring-pine/20 font-semibold"
                      : isPast
                        ? "bg-pine/15 text-pine border-pine/30 hover:bg-pine/25"
                        : "bg-ink/5 text-ink/60 border-ink/10 hover:bg-ink/10"
                  }`}
                >
                  {meta?.[locale] ?? st}
                </button>
              );
            })}
          </div>
        </div>

        {/* Two-Column Bitrix24 Layout */}
        <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-12 divide-y md:divide-y-0 md:divide-x divide-ink/10">
          {/* Left Column: Properties */}
          <div className="md:col-span-5 p-6 bg-paper/30 space-y-6 overflow-y-auto">
            <div>
              <h3 className="text-xs uppercase tracking-wider text-ink/45 font-semibold mb-3">О сделке</h3>
              <div className="space-y-3 text-sm">
                <div>
                  <span className="block text-xs text-ink/50">Сумма сделки:</span>
                  <span className="text-base font-bold text-pine">{money(currentDeal.amount_kzt, locale)}</span>
                </div>
                <div>
                  <span className="block text-xs text-ink/50">Клиент / Заказчик:</span>
                  <p className="font-medium text-ink">{currentDeal.client_name || "Алия Касымова"}</p>
                  {currentDeal.client_phone && (
                    <a
                      href={`tel:${currentDeal.client_phone}`}
                      className="inline-flex items-center gap-1 text-xs text-pine underline mt-0.5"
                    >
                      📞 {currentDeal.client_phone}
                    </a>
                  )}
                </div>

                {currentDeal.specialist_id && (
                  <div>
                    <span className="block text-xs text-ink/50">Подрядчик / Исполнитель:</span>
                    <span className="text-xs font-medium text-ink">
                      {currentDeal.specialist_name || currentDeal.specialist_id}
                    </span>
                  </div>
                )}
                <div>
                  <span className="block text-xs text-ink/50">Ответственный менеджер:</span>
                  <span className="text-xs font-medium text-ink">{currentDeal.responsible_name || "Асет Сагинтаев"}</span>
                </div>
                <div>
                  <span className="block text-xs text-ink/50">Источник:</span>
                  <span className="text-xs bg-ink/10 px-2 py-0.5 rounded text-ink/80">{currentDeal.source || "Сайт"}</span>
                </div>
              </div>
            </div>

            {/* Quick Link to Chat */}
            <div className="p-3 bg-white rounded-lg border border-ink/10">
              <span className="text-xs font-medium text-ink block mb-1">Коммуникация с клиентом</span>
              <p className="text-xs text-ink/60 mb-2">Переписка защищена внутри ANYQ SuperApp.</p>
              <Link
                href={`/${locale}/chat`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-pine text-white text-xs rounded font-medium hover:bg-pine/90"
              >
                💬 Открыть диалог в чате
              </Link>
            </div>

            {/* ConTech SuperApp Integration: ProjectHub Transfer */}
            {(currentDeal.funnel === "construction" || currentDeal.funnel === "design") && (
              <div className="p-4 bg-amber-50/70 border border-amber-200 rounded-lg">
                <span className="text-xs font-semibold uppercase tracking-wider text-amber-900 block mb-1">
                  🏗️ Интеграция с ProjectHub (СМР)
                </span>
                <p className="text-xs text-amber-800/80 mb-3">
                  Свяжите сделку со строительной площадкой: передайте смету, ведомости объемов и журнал работ.
                </p>
                {projectCreated ? (
                  <Link
                    href={`/${locale}/site/${projectCreated}`}
                    className="block text-center py-2 px-3 bg-pine text-white text-xs font-medium rounded hover:bg-pine/90"
                  >
                    Перейти на объект в ProjectHub →
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={handleConvertToProject}
                    className="w-full py-2 px-3 bg-amber-600 text-white text-xs font-semibold rounded hover:bg-amber-700 shadow-sm"
                  >
                    🚀 Запустить стройку в ProjectHub
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Right Column: Bitrix24 Timeline & Activity Composer */}
          <div className="md:col-span-7 p-6 flex flex-col space-y-6 overflow-y-auto">
            {/* Activity Composer Tabs */}
            <div className="bg-paper p-4 rounded-xl border border-ink/10 shadow-xs">
              <div className="flex gap-1 mb-3 border-b border-ink/10 pb-2 overflow-x-auto">
                {(["note", "call", "site_visit", "task", "invoice"] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setComposerTab(tab)}
                    className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
                      composerTab === tab ? "bg-pine text-white" : "text-ink/60 hover:text-ink hover:bg-ink/5"
                    }`}
                  >
                    {ACTIVITY_TYPE[tab]?.icon} {ACTIVITY_TYPE[tab]?.ru ?? tab}
                  </button>
                ))}
              </div>

              <form onSubmit={handleComposerSubmit} className="space-y-3">
                {composerTab === "invoice" ? (
                  <>
                    <input
                      type="text"
                      placeholder="Назначение платежа (напр. Задаток 10% через Эскроу)"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-ink/15 rounded bg-white"
                      required
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="number"
                        placeholder="Сумма в тенге"
                        value={invoiceAmount || ""}
                        onChange={(e) => setInvoiceAmount(Number(e.target.value))}
                        className="px-3 py-1.5 text-sm border border-ink/15 rounded bg-white"
                        required
                      />
                      <input
                        type="text"
                        placeholder="Плательщик (ФИО / ТОО)"
                        value={invoicePayer}
                        onChange={(e) => setInvoicePayer(e.target.value)}
                        className="px-3 py-1.5 text-sm border border-ink/15 rounded bg-white"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="text"
                        placeholder="ИИН / БИН плательщика"
                        value={invoiceIin}
                        onChange={(e) => setInvoiceIin(e.target.value)}
                        className="px-3 py-1.5 text-sm border border-ink/15 rounded bg-white"
                      />
                      <input
                        type="date"
                        value={dueDate}
                        onChange={(e) => setDueDate(e.target.value)}
                        className="px-3 py-1.5 text-sm border border-ink/15 rounded bg-white"
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <input
                      type="text"
                      placeholder={
                        composerTab === "call"
                          ? "Результат звонка или тема..."
                          : composerTab === "site_visit"
                            ? "Выезд на объект (напр. Вынос границ с геодезистом)..."
                            : composerTab === "task"
                              ? "Суть задачи (напр. Подготовить спецификацию к среде)..."
                              : "Заметка к сделке..."
                      }
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-ink/15 rounded bg-white"
                      required
                    />
                    <textarea
                      placeholder="Подробности, договорённости, комментарии..."
                      rows={2}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="w-full px-3 py-2 text-xs border border-ink/15 rounded bg-white"
                    />
                    {(composerTab === "call" || composerTab === "site_visit" || composerTab === "task") && (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-ink/50">Дедлайн / Дата:</span>
                        <input
                          type="date"
                          value={dueDate}
                          onChange={(e) => setDueDate(e.target.value)}
                          className="px-2 py-1 text-xs border border-ink/15 rounded bg-white"
                        />
                      </div>
                    )}
                  </>
                )}

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="px-4 py-1.5 bg-pine text-white text-xs font-semibold rounded hover:bg-pine/90 transition-colors shadow-xs"
                  >
                    {submitting ? "Сохранение..." : composerTab === "invoice" ? "Выставить счет ANYQ" : "Зафиксировать в таймлайне"}
                  </button>
                </div>
              </form>
            </div>

            {/* Invoices List */}
            {invoices.length > 0 && (
              <div>
                <h3 className="text-xs uppercase tracking-wider text-ink/45 font-semibold mb-2">
                  🧾 Счета сделки ({invoices.length})
                </h3>
                <div className="space-y-2">
                  {invoices.map((inv) => (
                    <div
                      key={inv.id}
                      className="p-3 bg-white rounded-lg border border-ink/10 flex items-center justify-between text-xs"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-ink">{inv.number}</span>
                          <span
                            className={`px-2 py-0.5 rounded font-medium text-[10px] ${
                              INVOICE_STATUS[inv.status]?.color ?? "bg-gray-100"
                            }`}
                          >
                            {INVOICE_STATUS[inv.status]?.ru ?? inv.status}
                          </span>
                        </div>
                        <p className="text-ink/75 mt-0.5">{inv.title}</p>
                        <p className="text-ink/45 text-[11px]">Плательщик: {inv.payer_name}</p>
                      </div>
                      <div className="text-right">
                        <span className="font-bold text-sm text-pine block font-mono">{money(inv.amount_kzt, locale)}</span>
                        {inv.status !== "paid" && (
                          <button
                            type="button"
                            onClick={() => handlePayInvoice(inv.id)}
                            className="mt-1 px-2.5 py-1 bg-emerald-600 text-white rounded text-[11px] font-medium hover:bg-emerald-700 shadow-xs"
                          >
                            💳 Оплатить (Kaspi Эскроу)
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Bitrix24 Timeline Feed */}
            <div>
              <h3 className="text-xs uppercase tracking-wider text-ink/45 font-semibold mb-3">
                🕒 Таймлайн и история активности
              </h3>
              {loading ? (
                <p className="text-xs text-ink/45">Загрузка ленты...</p>
              ) : activities.length === 0 ? (
                <p className="text-xs text-ink/45 italic">Событий пока нет. Создайте первую заметку или запланируйте звонок.</p>
              ) : (
                <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-ink/10">
                  {activities.map((act) => {
                    const meta = ACTIVITY_TYPE[act.activity_type];
                    return (
                      <div key={act.id} className="relative group">
                        {/* Timeline Pin */}
                        <div
                          className={`absolute -left-6 top-1 h-5 w-5 rounded-full grid place-items-center text-[10px] border shadow-xs ${
                            act.completed
                              ? "bg-emerald-100 border-emerald-400 text-emerald-800"
                              : "bg-white border-ink/20 text-ink"
                          }`}
                        >
                          {act.completed ? "✓" : meta?.icon ?? "•"}
                        </div>

                        {/* Timeline Card */}
                        <div className="p-3 bg-white rounded-lg border border-ink/10 shadow-2xs hover:border-ink/25 transition-colors">
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] font-semibold uppercase tracking-wider text-pine">
                                {meta?.ru ?? act.activity_type}
                              </span>
                              <span className="text-[11px] text-ink/40">•</span>
                              <span className="text-[11px] text-ink/45">{act.created_at.slice(0, 16).replace("T", " ")}</span>
                            </div>
                            <label className="flex items-center gap-1.5 text-xs text-ink/60 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={act.completed}
                                onChange={() => handleToggleActivity(act.id, act.completed)}
                                className="rounded text-pine focus:ring-pine/30"
                              />
                              <span className={act.completed ? "line-through text-ink/40 text-[11px]" : "text-[11px]"}>
                                {act.completed ? "Выполнено" : "К выполнению"}
                              </span>
                            </label>
                          </div>

                          <h4 className={`text-sm font-medium mt-1 text-ink ${act.completed ? "line-through text-ink/50" : ""}`}>
                            {act.title}
                          </h4>

                          {act.description && (
                            <p className="text-xs text-ink/60 mt-1 whitespace-pre-wrap">{act.description}</p>
                          )}

                          <div className="flex items-center justify-between mt-2 pt-2 border-t border-ink/5 text-[11px] text-ink/45">
                            <span>Автор: {act.author_name || "Менеджер"}</span>
                            {act.due_date && <span className="font-mono text-amber-700">Срок: {act.due_date}</span>}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
