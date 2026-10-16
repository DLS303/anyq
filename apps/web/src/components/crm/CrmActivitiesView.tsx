"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { createActivity, fetchActivities, toggleActivity } from "@/lib/api";
import { ACTIVITY_TYPE } from "@/lib/format";
import type { ActivityType, CrmActivity, Locale } from "@/lib/types";

export function CrmActivitiesView({
  locale,
  onSelectDealId,
}: {
  locale: Locale;
  onSelectDealId: (dealId: string) => void;
}) {
  const { user } = useAuth();
  const [activities, setActivities] = useState<CrmActivity[]>([]);
  const [filterType, setFilterType] = useState<string>("");
  const [onlyPending, setOnlyPending] = useState(false);
  const [loading, setLoading] = useState(true);

  // New activity modal
  const [isCreating, setIsCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newType, setNewType] = useState<ActivityType>("call");
  const [newDueDate, setNewDueDate] = useState("");

  function load() {
    if (!user) return;
    setLoading(true);
    fetchActivities(user.email)
      .then(setActivities)
      .catch(() => setActivities([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function handleToggle(id: string, current: boolean) {
    if (!user) return;
    try {
      await toggleActivity(user.email, id, !current);
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!user || !newTitle.trim()) return;
    try {
      await createActivity(user.email, {
        activity_type: newType,
        title: newTitle.trim(),
        description: newDesc.trim(),
        due_date: newDueDate,
      });
      setIsCreating(false);
      setNewTitle("");
      setNewDesc("");
      setNewDueDate("");
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  const filtered = activities.filter((a) => {
    if (onlyPending && a.completed) return false;
    if (filterType && a.activity_type !== filterType) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Filters Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-4 rounded-xl border border-ink/10 shadow-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setFilterType("")}
            className={`px-3 py-1 text-xs rounded-full border transition-all ${
              !filterType ? "bg-pine text-white border-pine font-medium shadow-xs" : "border-ink/15 text-ink/70 hover:bg-ink/5"
            }`}
          >
            Все дела ({activities.length})
          </button>
          {(["call", "site_visit", "task", "invoice", "note"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setFilterType(t)}
              className={`px-3 py-1 text-xs rounded-full border transition-all ${
                filterType === t ? "bg-pine text-white border-pine font-medium shadow-xs" : "border-ink/15 text-ink/70 hover:bg-ink/5"
              }`}
            >
              {ACTIVITY_TYPE[t]?.icon} {ACTIVITY_TYPE[t]?.ru ?? t}
            </button>
          ))}
          <label className="flex items-center gap-1.5 text-xs text-ink/70 ml-2 cursor-pointer">
            <input
              type="checkbox"
              checked={onlyPending}
              onChange={(e) => setOnlyPending(e.target.checked)}
              className="rounded text-pine"
            />
            <span>Только невыполненные</span>
          </label>
        </div>

        <button
          type="button"
          onClick={() => setIsCreating(true)}
          className="px-4 py-1.5 bg-pine text-white text-xs font-semibold rounded-lg hover:bg-pine/90 transition-colors shadow-xs flex items-center gap-1.5"
        >
          <span>+</span> Запланировать дело
        </button>
      </div>

      {/* Activities Feed */}
      <div className="space-y-2.5">
        {loading ? (
          <div className="py-12 text-center text-xs text-ink/40">Загрузка задач и дел...</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-xs text-ink/40 italic bg-white rounded-xl border border-ink/10">
            Дел не найдено
          </div>
        ) : (
          filtered.map((act) => {
            const meta = ACTIVITY_TYPE[act.activity_type];
            return (
              <div
                key={act.id}
                className={`p-4 rounded-xl border transition-all flex items-start justify-between gap-4 ${
                  act.completed ? "bg-paper/40 border-ink/10 opacity-75" : "bg-white border-ink/15 shadow-xs hover:border-pine/30"
                }`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={act.completed}
                    onChange={() => handleToggle(act.id, act.completed)}
                    className="mt-1 h-4 w-4 rounded text-pine cursor-pointer"
                  />
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-pine flex items-center gap-1">
                        <span>{meta?.icon}</span> {meta?.ru ?? act.activity_type}
                      </span>
                      <span className="text-ink/30">•</span>
                      <span className="text-[11px] text-ink/45">{act.created_at.slice(0, 16).replace("T", " ")}</span>
                      {act.due_date && (
                        <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-semibold font-mono">
                          ⏰ Срок: {act.due_date}
                        </span>
                      )}
                    </div>

                    <h4 className={`text-sm font-semibold text-ink ${act.completed ? "line-through text-ink/50" : ""}`}>
                      {act.title}
                    </h4>

                    {act.description && (
                      <p className="text-xs text-ink/65 mt-1 whitespace-pre-wrap">{act.description}</p>
                    )}

                    <div className="flex items-center gap-3 mt-2 text-[11px] text-ink/45">
                      <span>Ответственный: {act.author_name || "Менеджер"}</span>
                      {act.deal_id && (
                        <button
                          type="button"
                          onClick={() => onSelectDealId(act.deal_id!)}
                          className="text-pine underline font-medium hover:text-pine/80"
                        >
                          Сделка #{act.deal_id} →
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => handleToggle(act.id, act.completed)}
                  className={`px-3 py-1 rounded text-xs font-medium border transition-colors ${
                    act.completed
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : "bg-paper text-ink/70 border-ink/15 hover:bg-pine hover:text-white"
                  }`}
                >
                  {act.completed ? "✓ Выполнено" : "Выполнить"}
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Modal */}
      {isCreating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4 animate-fadeIn">
          <div className="w-full max-w-md bg-white rounded-2xl p-6 shadow-2xl border border-ink/15">
            <h3 className="text-lg font-serif font-bold text-ink mb-1">Запланировать дело / задачу</h3>
            <p className="text-xs text-ink/60 mb-4">Назначьте звонок клиенту, выезд на объект или составление сметы.</p>

            <form onSubmit={handleCreate} className="space-y-3 text-xs">
              <div>
                <label className="block text-ink/60 font-medium mb-1">Тип активности:</label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value as ActivityType)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                >
                  <option value="call">📞 Звонок клиенту</option>
                  <option value="site_visit">📍 Выезд на объект / Осмотр</option>
                  <option value="meeting">🤝 Встреча / Переговоры</option>
                  <option value="task">📋 Задача / Поручение</option>
                  <option value="note">📝 Заметка в систему</option>
                </select>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Название / Тема:</label>
                <input
                  type="text"
                  placeholder="напр. Контрольный звонок по условиям задатка"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  required
                />
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Дата и время выполнения:</label>
                <input
                  type="date"
                  value={newDueDate}
                  onChange={(e) => setNewDueDate(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                />
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Описание / Детали:</label>
                <textarea
                  rows={3}
                  placeholder="Что нужно обсудить или подготовить..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
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
                  Запланировать
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
