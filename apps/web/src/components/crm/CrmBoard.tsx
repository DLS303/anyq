"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { createDeal, fetchDeals, fetchFunnels, moveDeal } from "@/lib/api";
import { FUNNEL } from "@/lib/format";
import type { Deal, Funnel, Locale } from "@/lib/types";
import { t } from "@/i18n/messages";
import { CrmKanban } from "./CrmKanban";
import { CrmListView } from "./CrmListView";
import { CrmDealDrawer } from "./CrmDealDrawer";
import dynamic from "next/dynamic";

const CrmLeadsView = dynamic(
  () => import("./CrmLeadsView").then((m) => m.CrmLeadsView),
  { ssr: false, loading: () => <div className="p-8 text-center text-ink/50">Загрузка лидов...</div> }
);
const CrmContactsView = dynamic(
  () => import("./CrmContactsView").then((m) => m.CrmContactsView),
  { ssr: false, loading: () => <div className="p-8 text-center text-ink/50">Загрузка контактов...</div> }
);
const CrmActivitiesView = dynamic(
  () => import("./CrmActivitiesView").then((m) => m.CrmActivitiesView),
  { ssr: false, loading: () => <div className="p-8 text-center text-ink/50">Загрузка задач...</div> }
);
const CrmInvoicesView = dynamic(
  () => import("./CrmInvoicesView").then((m) => m.CrmInvoicesView),
  { ssr: false, loading: () => <div className="p-8 text-center text-ink/50">Загрузка счетов...</div> }
);
const CrmAnalyticsView = dynamic(
  () => import("./CrmAnalyticsView").then((m) => m.CrmAnalyticsView),
  { ssr: false, loading: () => <div className="p-8 text-center text-ink/50">Загрузка аналитики...</div> }
);
const CrmChessView = dynamic(
  () => import("./CrmChessView").then((m) => m.CrmChessView),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center p-12 text-ink/50 glass rounded-2xl">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-pine mr-3" />
        Загрузка интерактивной шахматки и генплана...
      </div>
    ),
  }
);

type CrmTab = "deals" | "leads" | "contacts" | "activities" | "invoices" | "analytics" | "chess";
type ViewMode = "kanban" | "list";

export function CrmBoard({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState<CrmTab>("deals");
  const [viewMode, setViewMode] = useState<ViewMode>("kanban");
  const [funnel, setFunnel] = useState<Funnel>("land_sale");
  const [stages, setStages] = useState<Record<string, string[]>>({});
  const [deals, setDeals] = useState<Deal[]>([]);
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);

  // New Deal Modal
  const [isCreatingDeal, setIsCreatingDeal] = useState(false);
  const [dealTitle, setDealTitle] = useState("");
  const [dealAmount, setDealAmount] = useState(0);
  const [dealClientName, setDealClientName] = useState("");
  const [dealClientPhone, setDealClientPhone] = useState("");
  const [dealNotes, setDealNotes] = useState("");

  function loadDeals() {
    if (!user) return;
    fetchDeals(user.email, funnel)
      .then(setDeals)
      .catch(() => setDeals([]));
  }

  useEffect(() => {
    fetchFunnels()
      .then(setStages)
      .catch(() => setStages({}));
  }, []);

  useEffect(() => {
    loadDeals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, funnel]);

  async function handleMove(dealId: string, stage: string) {
    if (!user) return;
    try {
      await moveDeal(user.email, dealId, stage);
      loadDeals();
      if (selectedDeal && selectedDeal.id === dealId) {
        setSelectedDeal((prev) => (prev ? { ...prev, stage } : null));
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function handleCreateDealSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user || !dealTitle.trim()) return;
    try {
      const created = await createDeal(user.email, {
        funnel,
        title: dealTitle.trim(),
        amount_kzt: Number(dealAmount),
        client_name: dealClientName.trim(),
        client_phone: dealClientPhone.trim(),
        notes: dealNotes.trim(),
      });
      setIsCreatingDeal(false);
      setDealTitle("");
      setDealAmount(0);
      setDealClientName("");
      setDealClientPhone("");
      setDealNotes("");
      loadDeals();
      setSelectedDeal(created);
    } catch (err) {
      alert((err as Error).message);
    }
  }

  if (!user) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-ink/65 mb-3">Для работы в CRM-системе войдите под демо-пользователем.</p>
        <Link href={`/${locale}/login`} className="btn-ice text-sm !py-2 !px-5 inline-block">
          {m.navLogin}
        </Link>
      </div>
    );
  }

  const columns = stages[funnel] ?? [];

  return (
    <div className="space-y-5">
      {/* Bitrix24 Top Navigation Header */}
      <div className="bg-white rounded-2xl border border-ink/10 p-4 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-ink/10">
          <div>
            <div className="flex items-center gap-2">
              <span className="grid place-items-center h-7 w-7 rounded-lg bg-pine text-white text-xs font-bold">
                B24
              </span>
              <h2 className="text-lg font-serif font-bold text-ink tracking-tight">
                CRM ANYQ · Продажи и Строительство
              </h2>
            </div>
            <p className="text-xs text-ink/50 mt-0.5">
              Сквозная воронка: земля → изыскания → проектирование → поставка стройматериалов → СМР
            </p>
          </div>

          {/* Global Quick Action */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsCreatingDeal(true)}
              className="px-4 py-2 bg-pine text-white text-xs font-semibold rounded-lg hover:bg-pine/90 transition-colors shadow-xs flex items-center gap-1.5"
            >
              <span>+</span> Новая сделка
            </button>
          </div>
        </div>

        {/* Top Entity Tabs */}
        <div className="flex items-center gap-1.5 pt-3 overflow-x-auto">
          {[
            { id: "deals", label: "💼 Сделки", desc: "Воронки продаж" },
            { id: "leads", label: "📥 Лиды", desc: "Входящие заявки" },
            { id: "contacts", label: "👥 Контакты & Компании", desc: "База контрагентов" },
            { id: "activities", label: "📋 Дела & Задачи", desc: "Звонки и выезды" },
            { id: "invoices", label: "🧾 Счета & Эскроу", desc: "Оплаты Kaspi" },
            { id: "analytics", label: "📊 Воронка & Аналитика", desc: "KPI и конверсия" },
            { id: "chess", label: "🏗 Шахматка", desc: "Генплан и сетка квартир" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as CrmTab)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === tab.id
                  ? "bg-pine text-white shadow-xs font-semibold"
                  : "text-ink/65 hover:text-ink hover:bg-ink/5"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Sub-bar for Deals Tab: Funnel selection and Kanban/List toggle */}
      {activeTab === "deals" && (
        <div className="flex flex-wrap items-center justify-between gap-3 bg-white/70 backdrop-blur-xs p-3.5 rounded-xl border border-ink/10 shadow-xs">
          {/* 5 Funnels Switcher */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-ink/50 uppercase tracking-wider mr-1">Воронка:</span>
            {(["land_sale", "design", "construction", "materials", "legal"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFunnel(f)}
                className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
                  funnel === f
                    ? "bg-pine text-white border-pine font-semibold shadow-xs"
                    : "border-ink/15 text-ink/70 hover:bg-ink/5"
                }`}
              >
                {FUNNEL[f]?.[locale] ?? f}
              </button>
            ))}
          </div>

          {/* View Mode Toggle: Kanban vs List */}
          <div className="flex items-center gap-1 bg-paper p-1 rounded-lg border border-ink/10 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("kanban")}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                viewMode === "kanban" ? "bg-white text-pine font-semibold shadow-2xs" : "text-ink/60 hover:text-ink"
              }`}
            >
              Канбан
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                viewMode === "list" ? "bg-white text-pine font-semibold shadow-2xs" : "text-ink/60 hover:text-ink"
              }`}
            >
              Список
            </button>
          </div>
        </div>
      )}

      {/* Tab Views */}
      {activeTab === "deals" && viewMode === "kanban" && (
        <CrmKanban
          stages={columns}
          deals={deals}
          locale={locale}
          onSelectDeal={(d) => setSelectedDeal(d)}
          onMoveDeal={handleMove}
        />
      )}

      {activeTab === "deals" && viewMode === "list" && (
        <CrmListView
          deals={deals}
          stages={stages}
          locale={locale}
          onSelectDeal={(d) => setSelectedDeal(d)}
          onMoveDeal={handleMove}
        />
      )}

      {activeTab === "leads" && (
        <CrmLeadsView
          locale={locale}
          onDealCreated={() => {
            loadDeals();
            setActiveTab("deals");
          }}
        />
      )}

      {activeTab === "contacts" && <CrmContactsView locale={locale} />}

      {activeTab === "activities" && (
        <CrmActivitiesView
          locale={locale}
          onSelectDealId={(did) => {
            const found = deals.find((d) => d.id === did);
            if (found) {
              setSelectedDeal(found);
            } else {
              setSelectedDeal({
                id: did,
                funnel,
                stage: "lead",
                title: `Сделка #${did}`,
                amount_kzt: 0,
                client_id: null,
                owner_id: null,
                specialist_id: null,
                plot_id: null,
                order_id: null,
                created_at: new Date().toISOString(),
              });
            }
          }}
        />
      )}

      {activeTab === "invoices" && (
        <CrmInvoicesView
          locale={locale}
          onSelectDealId={(did) => {
            const found = deals.find((d) => d.id === did);
            if (found) {
              setSelectedDeal(found);
            }
          }}
        />
      )}

      {activeTab === "analytics" && <CrmAnalyticsView locale={locale} />}

      {activeTab === "chess" && <CrmChessView locale={locale} />}

      {/* Bitrix24 Deal Drawer Modal */}
      {selectedDeal && (
        <CrmDealDrawer
          deal={selectedDeal}
          stages={stages}
          locale={locale}
          onClose={() => setSelectedDeal(null)}
          onDealUpdated={loadDeals}
        />
      )}

      {/* Quick Create Deal Modal */}
      {isCreatingDeal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4 animate-fadeIn">
          <div className="w-full max-w-lg bg-white rounded-2xl p-6 shadow-2xl border border-ink/15">
            <h3 className="text-lg font-serif font-bold text-ink mb-1">Создать новую сделку</h3>
            <p className="text-xs text-ink/60 mb-4">Внесите сделку в выбранную отраслевую воронку.</p>

            <form onSubmit={handleCreateDealSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-ink/60 font-medium mb-1">Направление / Воронка:</label>
                <select
                  value={funnel}
                  onChange={(e) => setFunnel(e.target.value as Funnel)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white font-medium"
                >
                  <option value="land_sale">Продажа участка (Земля)</option>
                  <option value="design">Проектирование / ПСД (Архитектура)</option>
                  <option value="construction">Строительство / СМР (Генподряд)</option>
                  <option value="materials">Поставка материалов (Бетон/Арматура)</option>
                  <option value="legal">Юр. оформление / ГАСК</option>
                </select>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Название сделки:</label>
                <input
                  type="text"
                  placeholder="напр. Ремизовка — подбор участка под коттедж"
                  value={dealTitle}
                  onChange={(e) => setDealTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Сумма сделки (₸):</label>
                  <input
                    type="number"
                    placeholder="0 ₸"
                    value={dealAmount || ""}
                    onChange={(e) => setDealAmount(Number(e.target.value))}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white font-mono"
                    required
                  />
                </div>
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Имя клиента:</label>
                  <input
                    type="text"
                    placeholder="ФИО заказчика"
                    value={dealClientName}
                    onChange={(e) => setDealClientName(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Телефон клиента:</label>
                <input
                  type="tel"
                  placeholder="+7 (701) 000-00-00"
                  value={dealClientPhone}
                  onChange={(e) => setDealClientPhone(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                />
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Примечания / Описание:</label>
                <textarea
                  rows={2}
                  placeholder="Ключевые договоренности или пожелания клиента..."
                  value={dealNotes}
                  onChange={(e) => setDealNotes(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-ink/10">
                <button
                  type="button"
                  onClick={() => setIsCreatingDeal(false)}
                  className="px-4 py-2 border border-ink/15 rounded-lg hover:bg-ink/5"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-pine text-white font-semibold rounded-lg hover:bg-pine/90 shadow-xs"
                >
                  Создать сделку
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
