"use client";

import { useState } from "react";
import { ChunkFallback } from "@/components/ui/ChunkFallback";
import { WidgetBoundary } from "@/components/ui/WidgetBoundary";
import { loadWithin } from "@/lib/loadWithin";
import { ErrorRetry, useAsync, useSubmitLock } from "@/lib/useAsync";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { createDeal, fetchDeals, fetchFunnels, moveDeal } from "@/lib/api";
import { FUNNEL, PRODUCT_FUNNELS } from "@/lib/format";
import type { Deal, Funnel, Locale } from "@/lib/types";
import { features } from "@/lib/features";
import { useMessages } from "@/lib/i18n";
import { CrmKanban } from "./CrmKanban";
import { CrmListView } from "./CrmListView";
import { CrmDealDrawer } from "./CrmDealDrawer";
import dynamic from "next/dynamic";

const CrmLeadsView = dynamic(() => loadWithin(import("./CrmLeadsView").then((m) => m.CrmLeadsView)), {
  ssr: false,
  loading: () => <ChunkFallback />,
});
const CrmContactsView = dynamic(() => loadWithin(import("./CrmContactsView").then((m) => m.CrmContactsView)), {
  ssr: false,
  loading: () => <ChunkFallback />,
});
const CrmActivitiesView = dynamic(() => loadWithin(import("./CrmActivitiesView").then((m) => m.CrmActivitiesView)), {
  ssr: false,
  loading: () => <ChunkFallback />,
});
const CrmInvoicesView = dynamic(() => loadWithin(import("./CrmInvoicesView").then((m) => m.CrmInvoicesView)), {
  ssr: false,
  loading: () => <ChunkFallback />,
});
const CrmAnalyticsView = dynamic(() => loadWithin(import("./CrmAnalyticsView").then((m) => m.CrmAnalyticsView)), {
  ssr: false,
  loading: () => <ChunkFallback />,
});
const CrmChessView = dynamic(() => loadWithin(import("./CrmChessView").then((m) => m.CrmChessView)), {
  ssr: false,
  loading: () => <ChunkFallback />,
});

type CrmTab = "deals" | "leads" | "contacts" | "activities" | "invoices" | "analytics" | "chess";
type ViewMode = "kanban" | "list";

export function CrmBoard({ locale }: { locale: Locale }) {
  const m = useMessages();
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState<CrmTab>("deals");
  const [viewMode, setViewMode] = useState<ViewMode>("kanban");
  const [funnel, setFunnel] = useState<Funnel>("construction");
  const stagesQuery = useAsync((signal) => fetchFunnels(signal), []);
  const dealsQuery = useAsync(
    (signal) => (user ? fetchDeals(user.email, funnel, signal) : Promise.resolve([] as Deal[])),
    [user?.email, funnel],
  );
  const stages = stagesQuery.data ?? {};
  const deals = dealsQuery.data ?? [];
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);

  // New Deal Modal
  const [isCreatingDeal, setIsCreatingDeal] = useState(false);
  const [createError, setCreateError] = useState("");
  const [dealTitle, setDealTitle] = useState("");
  const [dealAmount, setDealAmount] = useState(0);
  const [dealClientName, setDealClientName] = useState("");
  const [dealClientPhone, setDealClientPhone] = useState("");
  const [dealNotes, setDealNotes] = useState("");
  const createLock = useSubmitLock();

  function loadDeals() {
    dealsQuery.reload();
  }

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
    if (!user || createLock.pending) return;
    if (!dealTitle.trim()) {
      setCreateError(m.fieldRequired);
      return;
    }
    setCreateError("");
    await createLock.run(async () => {
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
    });
  }

  if (!user) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-ink/65 mb-3">{m.needLogin}</p>
        <Link href={`/${locale}/login`} className="btn-ice text-sm !py-2 !px-5 inline-block">
          {m.navLogin}
        </Link>
      </div>
    );
  }

  const columns = stages[funnel] ?? [];

  return (
    <div className="min-h-[100dvh] space-y-5">
      {/* Bitrix24 Top Navigation Header */}
      <div className="bg-white rounded-2xl border border-ink/10 p-4 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-ink/10">
          <div>
            <div className="flex items-center gap-2">
              <span className="grid place-items-center h-7 w-7 rounded-lg bg-pine text-white text-xs font-bold">
                B24
              </span>
              <h2 className="text-lg font-serif font-bold text-ink tracking-tight">{m.crmTitle}</h2>
            </div>
            <p className="text-xs text-ink/50 mt-0.5">{m.crmLead}</p>
          </div>

          {/* Global Quick Action */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsCreatingDeal(true)}
              className="px-4 py-2 bg-pine text-white text-xs font-semibold rounded-lg hover:bg-pine/90 transition-colors shadow-xs flex items-center gap-1.5"
            >
              <span>+</span> {m.crmNew}
            </button>
          </div>
        </div>

        {/* Top Entity Tabs */}
        <div className="tab-scroll pt-3">
          {[
            { id: "deals", label: m.crmDeals },
            { id: "leads", label: m.crmLeads },
            { id: "contacts", label: m.crmContacts },
            { id: "activities", label: m.crmActivities },
            { id: "invoices", label: m.crmInvoices },
            { id: "analytics", label: m.crmAnalytics },
            ...(features.chess ? [{ id: "chess", label: m.crmChess }] : []),
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as CrmTab)}
              className={`shrink-0 min-h-11 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
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
            <span className="text-xs font-semibold text-ink/50 uppercase tracking-wider mr-1">{m.crmFunnel}</span>
            {PRODUCT_FUNNELS.map((f) => (
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
              {m.crmKanban}
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                viewMode === "list" ? "bg-white text-pine font-semibold shadow-2xs" : "text-ink/60 hover:text-ink"
              }`}
            >
              {m.crmList}
            </button>
          </div>
        </div>
      )}

      {/* Tab Views */}
      {activeTab === "deals" && (dealsQuery.status === "error" || stagesQuery.status === "error") ? (
        <ErrorRetry message={m.listLoadError} retryLabel={m.hubRetry} onRetry={loadDeals} />
      ) : null}

      {activeTab === "deals" && dealsQuery.loading ? (
        <ChunkFallback />
      ) : null}

      {activeTab === "deals" && !dealsQuery.loading && viewMode === "kanban" && (
        <div className="min-h-[60vh]">
        <CrmKanban
          stages={columns}
          deals={deals}
          locale={locale}
          onSelectDeal={(d) => setSelectedDeal(d)}
          onMoveDeal={handleMove}
        />
        </div>
      )}

      {activeTab === "deals" && !dealsQuery.loading && viewMode === "list" && (
        <CrmListView
          email={user?.email ?? ""}
          funnel={funnel}
          refreshKey={deals.map((deal) => `${deal.id}:${deal.stage}`).join(",")}
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

      {activeTab === "analytics" && (
        <WidgetBoundary message={m.widgetError} retryLabel={m.retry}>
          <CrmAnalyticsView locale={locale} />
        </WidgetBoundary>
      )}

      {features.chess && activeTab === "chess" && (
        <WidgetBoundary message={m.widgetError} retryLabel={m.retry}>
          <CrmChessView locale={locale} />
        </WidgetBoundary>
      )}

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
            <h3 className="text-lg font-serif font-bold text-ink mb-1">{m.crmNew}</h3>
            <p className="text-xs text-ink/60 mb-4">{m.crmLead}</p>
            {createError ? <p className="mb-3 text-sm text-red-700" role="alert">{createError}</p> : null}

            <form onSubmit={handleCreateDealSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-ink/60 font-medium mb-1">{m.crmFunnel}</label>
                <select
                  value={funnel}
                  onChange={(e) => setFunnel(e.target.value as Funnel)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white font-medium"
                >
                  {PRODUCT_FUNNELS.map((id) => (
                    <option key={id} value={id}>
                      {FUNNEL[id]?.[locale] ?? id}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">{m.crmDeals}</label>
                <input
                  type="text"
                  placeholder="напр. Корпус Б — монолит, Наурыз"
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
                  disabled={createLock.pending}
                  className="min-h-11 rounded-lg bg-pine px-4 py-2 font-semibold text-white shadow-xs hover:bg-pine/90 disabled:opacity-50"
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
