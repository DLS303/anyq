"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { convertLead, createLead, fetchLeads } from "@/lib/api";
import { FUNNEL, LEAD_STATUS, PRODUCT_FUNNELS, money } from "@/lib/format";
import type { Funnel, Lead, Locale } from "@/lib/types";

export function CrmLeadsView({
  locale,
  onDealCreated,
}: {
  locale: Locale;
  onDealCreated: () => void;
}) {
  const { user } = useAuth();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  // Convert modal
  const [convertingLead, setConvertingLead] = useState<Lead | null>(null);
  const [targetFunnel, setTargetFunnel] = useState<Funnel>("construction");
  const [dealTitle, setDealTitle] = useState("");
  const [dealAmount, setDealAmount] = useState(0);

  // New lead modal
  const [isCreating, setIsCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newSource, setNewSource] = useState("Сайт");
  const [newFunnelTarget, setNewFunnelTarget] = useState<Funnel>("construction");
  const [newBudget, setNewBudget] = useState(0);
  const [newNotes, setNewNotes] = useState("");

  function load() {
    if (!user) return;
    setLoading(true);
    fetchLeads(user.email, statusFilter || undefined)
      .then(setLeads)
      .catch(() => setLeads([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, statusFilter]);

  async function handleConvertSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user || !convertingLead) return;
    try {
      await convertLead(user.email, convertingLead.id, {
        funnel: targetFunnel,
        deal_title: dealTitle || convertingLead.title,
        amount_kzt: Number(dealAmount) || convertingLead.budget_kzt,
      });
      setConvertingLead(null);
      load();
      onDealCreated();
      alert("Лид успешно сконвертирован в активную сделку!");
    } catch (err) {
      alert((err as Error).message);
    }
  }

  async function handleCreateLead(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim() || !newName.trim() || !newPhone.trim()) {
      alert("Заполните название, имя и телефон");
      return;
    }
    try {
      await createLead({
        title: newTitle.trim(),
        name: newName.trim(),
        phone: newPhone.trim(),
        email: newEmail.trim(),
        source: newSource,
        funnel_target: newFunnelTarget,
        budget_kzt: Number(newBudget),
        notes: newNotes.trim(),
      });
      setIsCreating(false);
      setNewTitle("");
      setNewName("");
      setNewPhone("");
      setNewEmail("");
      setNewNotes("");
      load();
      alert("Новый лид добавлен в CRM!");
    } catch (err) {
      alert((err as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      {/* Top action bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-4 rounded-xl border border-ink/10 shadow-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-ink/50 uppercase tracking-wider mr-1">Статус:</span>
          {[
            { id: "", label: "Все лиды" },
            { id: "new", label: "Новые" },
            { id: "contacted", label: "В обработке" },
            { id: "qualified", label: "Квалифицированные" },
            { id: "converted", label: "Сконвертированные" },
          ].map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setStatusFilter(s.id)}
              className={`px-3 py-1 text-xs rounded-full border transition-all ${
                statusFilter === s.id
                  ? "bg-pine text-white border-pine font-medium shadow-xs"
                  : "border-ink/15 text-ink/70 hover:bg-ink/5"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setIsCreating(true)}
          className="px-4 py-1.5 bg-pine text-white text-xs font-semibold rounded-lg hover:bg-pine/90 transition-colors shadow-xs flex items-center gap-1.5"
        >
          <span>+</span> Новый лид
        </button>
      </div>

      {/* Leads Table */}
      <div className="bg-white rounded-xl border border-ink/10 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-paper text-ink/60 border-b border-ink/10 uppercase tracking-wider font-semibold">
              <tr>
                <th className="py-3 px-4">Лид / Запрос</th>
                <th className="py-3 px-3">Контакт</th>
                <th className="py-3 px-3">Статус</th>
                <th className="py-3 px-3">Бюджет</th>
                <th className="py-3 px-3">Направление</th>
                <th className="py-3 px-3">Источник</th>
                <th className="py-3 px-3">Дата</th>
                <th className="py-3 px-4 text-right">Действие</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/5">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-ink/40">
                    Загрузка лидов...
                  </td>
                </tr>
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-ink/40 italic">
                    Лидов не найдено
                  </td>
                </tr>
              ) : (
                leads.map((lead) => (
                  <tr key={lead.id} className="hover:bg-pine/5 transition-colors">
                    <td className="py-3 px-4">
                      <div className="font-semibold text-sm text-ink">{lead.title}</div>
                      {lead.notes && <div className="text-[11px] text-ink/55 line-clamp-1">{lead.notes}</div>}
                    </td>
                    <td className="py-3 px-3">
                      <div className="font-medium text-ink">{lead.name}</div>
                      <a href={`tel:${lead.phone}`} className="text-[11px] text-pine underline block">
                        {lead.phone}
                      </a>
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          LEAD_STATUS[lead.status]?.color ?? "bg-gray-100"
                        }`}
                      >
                        {LEAD_STATUS[lead.status]?.ru ?? lead.status}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-bold font-mono text-pine">
                      {lead.budget_kzt ? money(lead.budget_kzt, locale) : "Не указан"}
                    </td>
                    <td className="py-3 px-3 text-ink/70">
                      {FUNNEL[lead.funnel_target === "land_sale" ? "construction" : lead.funnel_target]?.[locale] ?? lead.funnel_target}
                    </td>
                    <td className="py-3 px-3">
                      <span className="bg-ink/5 px-2 py-0.5 rounded text-[10px] text-ink/70">{lead.source}</span>
                    </td>
                    <td className="py-3 px-3 text-ink/45 font-mono text-[11px]">
                      {lead.created_at.slice(0, 10)}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {lead.status === "converted" ? (
                        <span className="text-[11px] text-emerald-700 font-medium">✓ В сделке</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            setConvertingLead(lead);
                            setDealTitle(lead.title);
                            setDealAmount(lead.budget_kzt || 0);
                            setTargetFunnel(
                              PRODUCT_FUNNELS.includes(lead.funnel_target as (typeof PRODUCT_FUNNELS)[number])
                                ? lead.funnel_target
                                : "construction",
                            );
                          }}
                          className="px-2.5 py-1 bg-pine text-white text-[11px] font-medium rounded hover:bg-pine/90 transition-colors shadow-2xs"
                        >
                          В сделку →
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Convert Lead Modal */}
      {convertingLead && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4 animate-fadeIn">
          <div className="w-full max-w-md bg-white rounded-2xl p-6 shadow-2xl border border-ink/15">
            <h3 className="text-lg font-serif font-bold text-ink mb-1">Конвертировать лид в сделку</h3>
            <p className="text-xs text-ink/60 mb-4">
              Выберите целевую отраслевую воронку и уточните сумму сделки.
            </p>

            <form onSubmit={handleConvertSubmit} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-ink/60 font-medium mb-1">Целевая воронка:</label>
                <select
                  value={targetFunnel}
                  onChange={(e) => setTargetFunnel(e.target.value as Funnel)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                >
                  <option value="construction">Строительство / СМР (Подряд)</option>
                  <option value="design">Проектирование / ПСД (Архитектура)</option>
                  <option value="materials">Поставка материалов (Бетон/Арматура)</option>
                  <option value="legal">Юр. оформление / ГАСК</option>
                </select>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Название сделки:</label>
                <input
                  type="text"
                  value={dealTitle}
                  onChange={(e) => setDealTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  required
                />
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Сумма сделки (₸):</label>
                <input
                  type="number"
                  value={dealAmount || ""}
                  onChange={(e) => setDealAmount(Number(e.target.value))}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-ink/10">
                <button
                  type="button"
                  onClick={() => setConvertingLead(null)}
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

      {/* New Lead Modal */}
      {isCreating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4 animate-fadeIn">
          <div className="w-full max-w-lg bg-white rounded-2xl p-6 shadow-2xl border border-ink/15">
            <h3 className="text-lg font-serif font-bold text-ink mb-1">Добавить новый лид</h3>
            <p className="text-xs text-ink/60 mb-4">Внесите обращение потенциального клиента в систему.</p>

            <form onSubmit={handleCreateLead} className="space-y-3 text-xs">
              <div>
                <label className="block text-ink/60 font-medium mb-1">Тема / Запрос:</label>
                <input
                  type="text"
                  placeholder="напр. Смета и генподряд на корпус в Алматы"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Имя клиента:</label>
                  <input
                    type="text"
                    placeholder="ФИО / Название"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                    required
                  />
                </div>
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Телефон:</label>
                  <input
                    type="tel"
                    placeholder="+7 (701) 000-00-00"
                    value={newPhone}
                    onChange={(e) => setNewPhone(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Целевое направление:</label>
                  <select
                    value={newFunnelTarget}
                    onChange={(e) => setNewFunnelTarget(e.target.value as Funnel)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  >
                    <option value="construction">Строительство / СМР</option>
                    <option value="design">Проектирование / ПСД</option>
                    <option value="materials">Поставка материалов</option>
                    <option value="legal">Юр. оформление</option>
                  </select>
                </div>
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Ориентир бюджета (₸):</label>
                  <input
                    type="number"
                    placeholder="Бюджет"
                    value={newBudget || ""}
                    onChange={(e) => setNewBudget(Number(e.target.value))}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Источник:</label>
                <select
                  value={newSource}
                  onChange={(e) => setNewSource(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                >
                  <option value="Сайт">Сайт</option>
                  <option value="WhatsApp">WhatsApp</option>
                  <option value="Входящий звонок">Входящий звонок</option>
                  <option value="Рекомендация">Рекомендация</option>
                  <option value="Заявка с объекта">Заявка с объекта</option>
                </select>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Примечания / Пожелания:</label>
                <textarea
                  rows={2}
                  placeholder="Дополнительные детали запроса..."
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-ink/10">
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="px-4 py-2 border border-ink/15 rounded-lg hover:bg-ink/5"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-pine text-white font-semibold rounded-lg hover:bg-pine/90 shadow-xs"
                >
                  Сохранить лид
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
