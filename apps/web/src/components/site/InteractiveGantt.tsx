"use client";

import React, { useMemo, useState, useRef } from "react";
import type { Locale, ScheduleTask, TaskStatus } from "@/lib/types";
import { postSite } from "@/lib/api";

type ViewMode = "day" | "week" | "month";

interface Props {
  locale: Locale;
  projectId: string;
  schedule: ScheduleTask[];
  email: string;
  onReload: () => void;
}

const RU_MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
];
const KK_MONTHS = [
  "Қаңтар", "Ақпан", "Наурыз", "Сәуір", "Мамыр", "Маусым",
  "Шілде", "Тамыз", "Қыркүйек", "Қазан", "Қараша", "Желтоқсан"
];
const RU_MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
const KK_MONTHS_SHORT = ["Қаң", "Ақп", "Нау", "Сәу", "Мам", "Мау", "Шіл", "Там", "Қыр", "Қаз", "Қар", "Жел"];

const RU_DAYS_SHORT = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
const KK_DAYS_SHORT = ["Жс", "Дс", "Сс", "Ср", "Бс", "Жм", "Сн"];

function parseLocalDate(str: string): Date {
  if (!str) return new Date();
  const parts = str.split("-").map(Number);
  if (parts.length >= 3 && !isNaN(parts[0]) && !isNaN(parts[1]) && !isNaN(parts[2])) {
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }
  return new Date(str);
}

function formatLocalDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function daysDiff(d1: Date, d2: Date): number {
  return Math.round((d2.getTime() - d1.getTime()) / (1000 * 60 * 60 * 24));
}

export function InteractiveGantt({ locale, projectId, schedule, email, onReload }: Props) {
  const isKk = locale === "kk";
  const [viewMode, setViewMode] = useState<ViewMode>("week");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduleTask | null>(null);
  const [saving, setSaving] = useState(false);
  const [hoveredTaskId, setHoveredTaskId] = useState<string | null>(null);

  // Form state
  const [formTitle, setFormTitle] = useState("");
  const [formStart, setFormStart] = useState("");
  const [formFinish, setFormFinish] = useState("");
  const [formPct, setFormPct] = useState(0);
  const [formStatus, setFormStatus] = useState<TaskStatus>("not_started");
  const [formDepends, setFormDepends] = useState("");

  const timelineContainerRef = useRef<HTMLDivElement>(null);

  // Filter tasks
  const filteredTasks = useMemo(() => {
    if (filterStatus === "all") return schedule;
    return schedule.filter((t) => t.status === filterStatus);
  }, [schedule, filterStatus]);

  // Overall bounds
  const { minDate, totalDays } = useMemo(() => {
    if (!schedule || schedule.length === 0) {
      const now = new Date();
      const end = new Date(now);
      end.setDate(end.getDate() + 60);
      return { minDate: now, totalDays: 60 };
    }

    let min = parseLocalDate(schedule[0].start);
    let max = parseLocalDate(schedule[0].finish);

    schedule.forEach((t) => {
      const s = parseLocalDate(t.start);
      const f = parseLocalDate(t.finish);
      if (s < min) min = s;
      if (f > max) max = f;
    });

    const paddedMin = new Date(min);
    paddedMin.setDate(paddedMin.getDate() - 4);
    const paddedMax = new Date(max);
    paddedMax.setDate(paddedMax.getDate() + 10);

    const diff = Math.max(14, daysDiff(paddedMin, paddedMax));
    return { minDate: paddedMin, totalDays: diff };
  }, [schedule]);

  const dayWidth = useMemo(() => {
    switch (viewMode) {
      case "day":
        return 38;
      case "week":
        return 16;
      case "month":
        return 5.5;
    }
  }, [viewMode]);

  const timelineWidth = Math.max(800, totalDays * dayWidth);
  const rowHeight = 44;
  const headerHeight = 56;
  const svgHeight = headerHeight + filteredTasks.length * rowHeight;

  const dateToX = (d: Date): number => {
    const diff = daysDiff(minDate, d);
    return diff * dayWidth;
  };

  const today = new Date();
  const todayX = dateToX(today);
  const showToday = todayX >= 0 && todayX <= timelineWidth;

  const headerStructure = useMemo(() => {
    const days: { date: Date; x: number; label: string; subLabel: string; isWeekend: boolean }[] = [];
    const months: { label: string; x: number; width: number }[] = [];

    let currentMonth = -1;
    let currentYear = -1;
    let monthStartX = 0;
    let monthLabel = "";

    for (let i = 0; i < totalDays; i++) {
      const d = new Date(minDate);
      d.setDate(d.getDate() + i);
      const x = i * dayWidth;
      const mIdx = d.getMonth();
      const y = d.getFullYear();
      const dayOfWeek = d.getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

      if (mIdx !== currentMonth || y !== currentYear) {
        if (currentMonth !== -1) {
          months.push({
            label: monthLabel,
            x: monthStartX,
            width: x - monthStartX,
          });
        }
        currentMonth = mIdx;
        currentYear = y;
        monthStartX = x;
        const mNames = isKk ? KK_MONTHS : RU_MONTHS;
        monthLabel = `${mNames[mIdx]} ${y}`;
      }

      if (viewMode === "day") {
        const dNames = isKk ? KK_DAYS_SHORT : RU_DAYS_SHORT;
        days.push({
          date: d,
          x,
          label: String(d.getDate()),
          subLabel: dNames[dayOfWeek],
          isWeekend,
        });
      } else if (viewMode === "week") {
        if (dayOfWeek === 1 || i === 0) {
          const shortMonths = isKk ? KK_MONTHS_SHORT : RU_MONTHS_SHORT;
          days.push({
            date: d,
            x,
            label: `${d.getDate()} ${shortMonths[mIdx]}`,
            subLabel: isKk ? `${Math.floor(i / 7) + 1}-апта` : `нед. ${Math.floor(i / 7) + 1}`,
            isWeekend: false,
          });
        }
      }
    }

    if (currentMonth !== -1) {
      months.push({
        label: monthLabel,
        x: monthStartX,
        width: timelineWidth - monthStartX,
      });
    }

    return { months, days };
  }, [minDate, totalDays, dayWidth, isKk, timelineWidth, viewMode]);

  const taskPositions = useMemo(() => {
    const map = new Map<string, { x: number; y: number; width: number; endX: number; index: number }>();
    filteredTasks.forEach((t, idx) => {
      const start = parseLocalDate(t.start);
      const finish = parseLocalDate(t.finish);
      const x = Math.max(0, dateToX(start));
      const width = Math.max(24, dateToX(finish) - x);
      const y = headerHeight + idx * rowHeight + (rowHeight - 26) / 2;
      map.set(t.id, { x, y, width, endX: x + width, index: idx });
    });
    return map;
  }, [filteredTasks, headerHeight, rowHeight, dateToX]);

  const dependencyLinks = useMemo(() => {
    const links: {
      fromId: string;
      toId: string;
      d: string;
      arrowX: number;
      arrowY: number;
    }[] = [];

    filteredTasks.forEach((task) => {
      if (!task.depends) return;
      const targetPos = taskPositions.get(task.id);
      const sourcePos = taskPositions.get(task.depends);
      if (!sourcePos || !targetPos) return;

      const x1 = sourcePos.endX;
      const y1 = sourcePos.y + 13;
      const x2 = targetPos.x;
      const y2 = targetPos.y + 13;

      let d = "";
      if (x2 >= x1 + 16) {
        const midX = (x1 + x2) / 2;
        d = `M ${x1} ${y1} H ${midX} V ${y2} H ${x2}`;
      } else {
        const stepX = x1 + 12;
        const stepY = y1 + (y2 > y1 ? 18 : -18);
        d = `M ${x1} ${y1} H ${stepX} V ${stepY} H ${x2 - 12} V ${y2} H ${x2}`;
      }

      links.push({
        fromId: task.depends,
        toId: task.id,
        d,
        arrowX: x2,
        arrowY: y2,
      });
    });

    return links;
  }, [filteredTasks, taskPositions]);

  async function handleQuickPct(task: ScheduleTask, delta: number) {
    const nextPct = Math.max(0, Math.min(100, task.pct + delta));
    try {
      await postSite(`schedule/${task.id}/progress`, email, { pct: nextPct });
      onReload();
    } catch (e) {
      console.error("Failed to update progress:", e);
    }
  }

  function openAddModal() {
    setEditingTask(null);
    setFormTitle("");
    const defStart = new Date();
    const defFinish = new Date();
    defFinish.setDate(defFinish.getDate() + 14);
    setFormStart(formatLocalDate(defStart));
    setFormFinish(formatLocalDate(defFinish));
    setFormPct(0);
    setFormStatus("not_started");
    setFormDepends(schedule.length > 0 ? schedule[schedule.length - 1].id : "");
    setIsModalOpen(true);
  }

  function openEditModal(task: ScheduleTask) {
    setEditingTask(task);
    setFormTitle(task.title);
    setFormStart(task.start);
    setFormFinish(task.finish);
    setFormPct(task.pct);
    setFormStatus(task.status);
    setFormDepends(task.depends || "");
    setIsModalOpen(true);
  }

  async function handleSaveTask(e: React.FormEvent) {
    e.preventDefault();
    if (!formTitle.trim()) return;
    setSaving(true);
    try {
      if (editingTask) {
        await postSite(`schedule/${editingTask.id}/update`, email, {
          title: formTitle.trim(),
          start: formStart,
          finish: formFinish,
          pct: formPct,
          status: formStatus,
          depends: formDepends || "",
        });
      } else {
        await postSite(`projects/${projectId}/schedule`, email, {
          title: formTitle.trim(),
          start: formStart,
          finish: formFinish,
          pct: formPct,
          status: formStatus,
          depends: formDepends || "",
        });
      }
      setIsModalOpen(false);
      onReload();
    } catch (err) {
      alert("Ошибка при сохранении: " + (err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteTask(taskId: string) {
    if (!confirm(isKk ? "Бұл жұмысты өшіруге сенімдісіз бе?" : "Удалить эту работу из графика?")) return;
    try {
      await postSite(`schedule/${taskId}/delete`, email);
      setIsModalOpen(false);
      onReload();
    } catch (err) {
      alert("Ошибка при удалении: " + (err as Error).message);
    }
  }

  function scrollToToday() {
    if (timelineContainerRef.current) {
      const scrollPos = Math.max(0, todayX - 250);
      timelineContainerRef.current.scrollTo({ left: scrollPos, behavior: "smooth" });
    }
  }

  const totalTasks = schedule.length;
  const completedTasks = schedule.filter((t) => t.status === "done" || t.pct >= 100).length;
  const inProgressTasks = schedule.filter((t) => t.status === "in_progress" || (t.pct > 0 && t.pct < 100)).length;
  const avgPct = totalTasks > 0 ? Math.round(schedule.reduce((acc, t) => acc + t.pct, 0) / totalTasks) : 0;

  return (
    <div className="bg-paper border border-ink/10 rounded-sm shadow-sm overflow-hidden text-ink">
      {/* Top Action Bar */}
      <div className="p-4 bg-mist/30 border-b border-ink/10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <h2 className="font-serif text-lg font-bold">
              {isKk ? "Құрылыс интерактивті Гант кестесі" : "Интерактивная диаграмма Ганта (SMR)"}
            </h2>
            <p className="text-xs text-ink/60">
              {isKk
                ? `${totalTasks} жұмыс кезеңі · Орташа орындалу: ${avgPct}%`
                : `${totalTasks} этапов работ · Средний прогресс: ${avgPct}% · Завершено: ${completedTasks}/${totalTasks}`}
            </p>
          </div>

          <div className="hidden sm:flex items-center gap-2 pl-4 border-l border-ink/15 text-xs">
            <span className="px-2 py-0.5 rounded bg-pine/10 text-pine font-medium">
              {isKk ? "Дайын" : "Готово"}: {completedTasks}
            </span>
            <span className="px-2 py-0.5 rounded bg-sky-600/10 text-sky-700 font-medium">
              {isKk ? "Орындалуда" : "В работе"}: {inProgressTasks}
            </span>
            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-700 font-medium">
              {avgPct}% {isKk ? "орташа" : "общий ход"}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex border border-ink/15 rounded bg-paper p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("day")}
              className={`px-2.5 py-1 rounded transition-colors ${
                viewMode === "day" ? "bg-pine text-paper font-medium" : "text-ink/70 hover:bg-mist"
              }`}
            >
              {isKk ? "Күн" : "День"}
            </button>
            <button
              type="button"
              onClick={() => setViewMode("week")}
              className={`px-2.5 py-1 rounded transition-colors ${
                viewMode === "week" ? "bg-pine text-paper font-medium" : "text-ink/70 hover:bg-mist"
              }`}
            >
              {isKk ? "Апта" : "Неделя"}
            </button>
            <button
              type="button"
              onClick={() => setViewMode("month")}
              className={`px-2.5 py-1 rounded transition-colors ${
                viewMode === "month" ? "bg-pine text-paper font-medium" : "text-ink/70 hover:bg-mist"
              }`}
            >
              {isKk ? "Ай" : "Месяц"}
            </button>
          </div>

          <button
            type="button"
            onClick={scrollToToday}
            className="px-2.5 py-1 text-xs border border-ink/15 rounded bg-paper hover:bg-mist transition-colors font-medium flex items-center gap-1"
          >
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            {isKk ? "Бүгін" : "Сегодня"}
          </button>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            aria-label={isKk ? "Сүзгі" : "Фильтр по статусу"}
            className="text-xs border border-ink/15 rounded px-2 py-1 bg-paper text-ink"
          >
            <option value="all">{isKk ? "Барлығы" : "Все статусы"}</option>
            <option value="in_progress">{isKk ? "Орындалуда" : "В работе"}</option>
            <option value="done">{isKk ? "Дайын" : "Завершенные"}</option>
            <option value="not_started">{isKk ? "Басталмаған" : "Не начаты"}</option>
            <option value="blocked">{isKk ? "Бұғатталған" : "Приостановлены"}</option>
          </select>

          <button
            type="button"
            onClick={openAddModal}
            className="px-3 py-1 bg-pine text-paper text-xs font-semibold rounded hover:bg-pine/90 transition-colors shadow-sm flex items-center gap-1"
          >
            <span>+</span>
            <span>{isKk ? "Жұмыс қосу" : "Добавить работу"}</span>
          </button>
        </div>
      </div>

      {/* Main Gantt Split Container */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-t border-ink/10">
        {/* Left Side: Tasks Table */}
        <div className="lg:col-span-5 xl:col-span-4 border-r border-ink/10 bg-paper overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-mist/50 border-b border-ink/10 h-[56px] text-ink/60 uppercase tracking-wider text-[10px]">
                <th className="px-3 py-2 font-semibold">{isKk ? "Кезең атауы" : "Этап / Работа"}</th>
                <th className="px-2 py-2 font-semibold w-24">{isKk ? "Мерзімі" : "Сроки"}</th>
                <th className="px-2 py-2 font-semibold w-20 text-center">{isKk ? "Орындалу" : "Прогресс"}</th>
                <th className="px-2 py-2 font-semibold w-16 text-right">{isKk ? "Әрекет" : "Действия"}</th>
              </tr>
            </thead>
            <tbody>
              {filteredTasks.length === 0 ? (
                <tr>
                  <td colSpan={4} className="p-6 text-center text-ink/40">
                    {isKk ? "Жұмыстар табылмады" : "Нет работ в выбранном фильтре"}
                  </td>
                </tr>
              ) : (
                filteredTasks.map((t) => {
                  const isHovered = hoveredTaskId === t.id;
                  const isSelected = selectedTaskId === t.id;
                  const duration = daysDiff(parseLocalDate(t.start), parseLocalDate(t.finish));

                  return (
                    <tr
                      key={t.id}
                      onMouseEnter={() => setHoveredTaskId(t.id)}
                      onMouseLeave={() => setHoveredTaskId(null)}
                      onClick={() => setSelectedTaskId(t.id)}
                      className={`h-[44px] border-b border-ink/5 transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-pine/10 font-medium"
                          : isHovered
                          ? "bg-mist/60"
                          : "hover:bg-mist/30"
                      }`}
                    >
                      <td className="px-3 py-1">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`w-2 h-2 rounded-full shrink-0 ${
                              t.status === "done" || t.pct >= 100
                                ? "bg-emerald-500"
                                : t.status === "in_progress"
                                ? "bg-sky-600"
                                : t.status === "blocked"
                                ? "bg-red-500"
                                : "bg-slate-400"
                            }`}
                          />
                          <span className="truncate max-w-[140px] sm:max-w-[180px] font-medium text-ink">
                            {t.title}
                          </span>
                          {t.depends && (
                            <span
                              title={`Зависит от: ${t.depends}`}
                              className="text-[9px] px-1 py-0.2 rounded bg-ink/5 text-ink/50 border border-ink/10 shrink-0"
                            >
                              ↳ {t.depends}
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="px-2 py-1 text-[11px] text-ink/70 whitespace-nowrap">
                        <div>
                          {t.start.slice(5)} → {t.finish.slice(5)}
                        </div>
                        <div className="text-[9px] text-ink/40">{duration} дн.</div>
                      </td>

                      <td className="px-2 py-1">
                        <div className="flex flex-col items-center gap-0.5">
                          <span className="text-[10px] font-semibold text-ink/80">{t.pct}%</span>
                          <div className="w-14 h-1.5 bg-mist rounded-full overflow-hidden border border-ink/10">
                            <div
                              className={`h-full rounded-full transition-all ${
                                t.pct >= 100 ? "bg-emerald-500" : "bg-pine"
                              }`}
                              style={{ width: `${t.pct}%` }}
                            />
                          </div>
                        </div>
                      </td>

                      <td className="px-2 py-1 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            title={isKk ? "+10% қосу" : "+10% к прогрессу"}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleQuickPct(t, 10);
                            }}
                            className="text-[10px] px-1 py-0.5 border border-ink/15 rounded hover:bg-pine hover:text-paper transition-colors"
                          >
                            +10%
                          </button>
                          <button
                            type="button"
                            title={isKk ? "Өзгерту" : "Редактировать"}
                            onClick={(e) => {
                              e.stopPropagation();
                              openEditModal(t);
                            }}
                            className="text-[11px] text-ink/50 hover:text-pine px-1"
                          >
                            ✎
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Right Side: Interactive SVG Timeline */}
        <div
          ref={timelineContainerRef}
          className="lg:col-span-7 xl:col-span-8 overflow-x-auto relative bg-[#FCFCFD] select-none"
          style={{ minHeight: "260px" }}
        >
          <svg
            width={timelineWidth}
            height={svgHeight}
            className="block"
            style={{ minWidth: `${timelineWidth}px` }}
          >
            <defs>
              <marker
                id="gantt-arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#2E75B6" />
              </marker>
              <marker
                id="gantt-arrow-highlight"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#0B1E3D" />
              </marker>

              <pattern
                id="progress-stripes"
                width="10"
                height="10"
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
              >
                <line x1="0" y1="0" x2="0" y2="10" stroke="rgba(255,255,255,0.15)" strokeWidth="4" />
              </pattern>
            </defs>

            {/* Header Background */}
            <rect x="0" y="0" width={timelineWidth} height={headerHeight} fill="#F4F5F7" />
            <line x1="0" y1={headerHeight} x2={timelineWidth} y2={headerHeight} stroke="#DDE1E6" strokeWidth="1" />

            {/* Month Headers */}
            {headerStructure.months.map((m, idx) => (
              <g key={`month-${idx}`}>
                <rect
                  x={m.x}
                  y="0"
                  width={m.width}
                  height="26"
                  fill="#EAECEF"
                  stroke="#DDE1E6"
                  strokeWidth="0.5"
                />
                <text
                  x={m.x + 8}
                  y="17"
                  fill="#2A384C"
                  fontSize="11"
                  fontWeight="600"
                  className="font-sans"
                >
                  {m.label}
                </text>
              </g>
            ))}

            {/* Sub-headers (Days or Weeks) */}
            {headerStructure.days.map((d, idx) => {
              const colWidth = viewMode === "day" ? dayWidth : dayWidth * 7;
              return (
                <g key={`day-hdr-${idx}`}>
                  <rect
                    x={d.x}
                    y="26"
                    width={colWidth}
                    height="30"
                    fill={d.isWeekend ? "#EDEDF0" : "#F8F9FA"}
                    stroke="#EAECEF"
                    strokeWidth="0.5"
                  />
                  <text
                    x={d.x + colWidth / 2}
                    y="42"
                    textAnchor="middle"
                    fill={d.isWeekend ? "#8C9BAE" : "#4A5568"}
                    fontSize="10"
                    fontWeight="500"
                  >
                    {d.label}
                  </text>
                  {d.subLabel && viewMode === "day" && (
                    <text
                      x={d.x + colWidth / 2}
                      y="52"
                      textAnchor="middle"
                      fill={d.isWeekend ? "#A0AEC0" : "#718096"}
                      fontSize="8"
                    >
                      {d.subLabel}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Vertical Grid Lines */}
            {headerStructure.days.map((d, idx) => (
              <line
                key={`grid-line-${idx}`}
                x1={d.x}
                y1={headerHeight}
                x2={d.x}
                y2={svgHeight}
                stroke={d.isWeekend ? "#F1F2F4" : "#F8F9FA"}
                strokeWidth={viewMode === "day" && d.isWeekend ? dayWidth : "1"}
                opacity={d.isWeekend ? "0.6" : "1"}
              />
            ))}

            {/* Alternating Row Lines */}
            {filteredTasks.map((_, idx) => {
              const y = headerHeight + idx * rowHeight;
              return (
                <g key={`row-${idx}`}>
                  <rect
                    x="0"
                    y={y}
                    width={timelineWidth}
                    height={rowHeight}
                    fill={idx % 2 === 0 ? "transparent" : "#FAFAFC"}
                    opacity="0.6"
                  />
                  <line
                    x1="0"
                    y1={y + rowHeight}
                    x2={timelineWidth}
                    y2={y + rowHeight}
                    stroke="#ECEEF2"
                    strokeWidth="1"
                  />
                </g>
              );
            })}

            {/* Today Line Indicator */}
            {showToday && (
              <g>
                <line
                  x1={todayX}
                  y1={0}
                  x2={todayX}
                  y2={svgHeight}
                  stroke="#E53E3E"
                  strokeWidth="2"
                  strokeDasharray="4 3"
                />
                <rect
                  x={todayX - 26}
                  y="2"
                  width="52"
                  height="18"
                  rx="3"
                  fill="#E53E3E"
                />
                <text
                  x={todayX}
                  y="14"
                  textAnchor="middle"
                  fill="#FFFFFF"
                  fontSize="9"
                  fontWeight="bold"
                >
                  {isKk ? "БҮГІН" : "СЕГОДНЯ"}
                </text>
              </g>
            )}

            {/* Predecessor Dependency Lines */}
            {dependencyLinks.map((link, idx) => {
              const isDepActive =
                hoveredTaskId === link.fromId ||
                hoveredTaskId === link.toId ||
                selectedTaskId === link.fromId ||
                selectedTaskId === link.toId;

              return (
                <g key={`dep-${idx}`}>
                  <path
                    d={link.d}
                    fill="none"
                    stroke={isDepActive ? "#0B1E3D" : "#2E75B6"}
                    strokeWidth={isDepActive ? "2.5" : "1.5"}
                    strokeDasharray={isDepActive ? "none" : "3 2"}
                    markerEnd={`url(#${isDepActive ? "gantt-arrow-highlight" : "gantt-arrow"})`}
                    opacity={isDepActive ? "1" : "0.75"}
                    className="transition-all"
                  />
                </g>
              );
            })}

            {/* Task Bars */}
            {filteredTasks.map((t) => {
              const pos = taskPositions.get(t.id);
              if (!pos) return null;

              const isHovered = hoveredTaskId === t.id;
              const isSelected = selectedTaskId === t.id;
              const isDone = t.pct >= 100 || t.status === "done";
              const isBlocked = t.status === "blocked";

              const barFill = isDone ? "#3CB878" : isBlocked ? "#E05656" : "#2E75B6";
              const barProgressFill = isDone ? "#2B8C5B" : isBlocked ? "#B83A3A" : "#0B1E3D";

              const barHeight = 26;
              const barY = pos.y;
              const progressWidth = Math.max(0, (pos.width * Math.min(100, t.pct)) / 100);

              return (
                <g
                  key={t.id}
                  className="cursor-pointer group"
                  onMouseEnter={() => setHoveredTaskId(t.id)}
                  onMouseLeave={() => setHoveredTaskId(null)}
                  onClick={() => openEditModal(t)}
                >
                  {(isHovered || isSelected) && (
                    <rect
                      x={pos.x - 3}
                      y={barY - 3}
                      width={pos.width + 6}
                      height={barHeight + 6}
                      rx="7"
                      fill="none"
                      stroke="#0B1E3D"
                      strokeWidth="2"
                      opacity="0.5"
                    />
                  )}

                  <rect
                    x={pos.x}
                    y={barY}
                    width={pos.width}
                    height={barHeight}
                    rx="5"
                    fill={barFill}
                    opacity={t.status === "not_started" ? "0.6" : "0.9"}
                    className="transition-all"
                  />

                  {progressWidth > 0 && (
                    <rect
                      x={pos.x}
                      y={barY}
                      width={progressWidth}
                      height={barHeight}
                      rx="5"
                      fill={barProgressFill}
                      opacity="0.95"
                    />
                  )}

                  {progressWidth > 0 && t.pct < 100 && (
                    <rect
                      x={pos.x}
                      y={barY}
                      width={progressWidth}
                      height={barHeight}
                      rx="5"
                      fill="url(#progress-stripes)"
                    />
                  )}

                  {pos.width > 70 ? (
                    <text
                      x={pos.x + 8}
                      y={barY + 17}
                      fill="#FFFFFF"
                      fontSize="11"
                      fontWeight="600"
                      className="pointer-events-none drop-shadow-sm select-none"
                    >
                      {t.title} · {t.pct}%
                    </text>
                  ) : (
                    <text
                      x={pos.endX + 6}
                      y={barY + 17}
                      fill="#2A384C"
                      fontSize="11"
                      fontWeight="600"
                      className="pointer-events-none select-none"
                    >
                      {t.title} ({t.pct}%)
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* Footer Instructions & Legend */}
      <div className="p-3 bg-mist/20 border-t border-ink/10 flex flex-wrap items-center justify-between text-xs text-ink/60 gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-[#3CB878]" />
            <span>{isKk ? "Дайын (100%)" : "Завершено (100%)"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-[#2E75B6]" />
            <span>{isKk ? "Орындалуда" : "В процессе"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-[#E05656]" />
            <span>{isKk ? "Бұғатталған" : "Остановлено / Риск"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-slate-400" />
            <span>{isKk ? "Жоспар" : "Не начато"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[#2E75B6] font-bold">↳ →</span>
            <span>{isKk ? "Байланыс сызықтары (Dependencies)" : "Связи и зависимости (Predecessors)"}</span>
          </div>
        </div>

        <p className="text-[11px] text-ink/40">
          {isKk
            ? "💡 Жұмысты басып өңдеңіз немесе +10% батырмасын басыңыз"
            : "💡 Нажмите на полосу задачи для редактирования или +10% для быстрого прогресса"}
        </p>
      </div>

      {/* Modal Dialog: Add / Edit Task */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-paper border border-ink/15 rounded-md shadow-xl w-full max-w-lg p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-ink/10 pb-3 mb-4">
              <h3 className="font-serif text-lg font-bold">
                {editingTask
                  ? isKk
                    ? `Жұмысты өңдеу: ${editingTask.title}`
                    : `Редактирование задачи: ${editingTask.title}`
                  : isKk
                  ? "Жаңа құрылыс жұмысын қосу"
                  : "Добавить этап / работу в график"}
              </h3>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-ink/40 hover:text-ink text-lg leading-none"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveTask} className="space-y-4 text-xs">
              <div>
                <label className="block font-medium mb-1 text-ink/75">
                  {isKk ? "Жұмыс атауы *" : "Название этапа / работы *"}
                </label>
                <input
                  type="text"
                  required
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  placeholder={isKk ? "Мысалы: Фундамент құю" : "Например: Заливка фундамента"}
                  className="w-full border border-ink/20 rounded px-3 py-2 bg-paper text-ink focus:outline-pine text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium mb-1 text-ink/75">
                    {isKk ? "Басталу күні *" : "Дата начала *"}
                  </label>
                  <input
                    type="date"
                    required
                    value={formStart}
                    onChange={(e) => setFormStart(e.target.value)}
                    className="w-full border border-ink/20 rounded px-3 py-1.5 bg-paper text-ink"
                  />
                </div>
                <div>
                  <label className="block font-medium mb-1 text-ink/75">
                    {isKk ? "Аяқталу күні *" : "Дата окончания *"}
                  </label>
                  <input
                    type="date"
                    required
                    value={formFinish}
                    onChange={(e) => setFormFinish(e.target.value)}
                    className="w-full border border-ink/20 rounded px-3 py-1.5 bg-paper text-ink"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="font-medium text-ink/75">
                    {isKk ? "Орындалу пайызы" : "Прогресс выполнения"}: <span className="text-pine font-bold">{formPct}%</span>
                  </label>
                  <div className="flex gap-1">
                    {[0, 25, 50, 75, 100].map((val) => (
                      <button
                        key={val}
                        type="button"
                        onClick={() => setFormPct(val)}
                        className="px-1.5 py-0.5 border border-ink/15 rounded text-[10px] hover:bg-mist"
                      >
                        {val}%
                      </button>
                    ))}
                  </div>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={formPct}
                  onChange={(e) => setFormPct(Number(e.target.value))}
                  className="w-full accent-pine cursor-pointer"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium mb-1 text-ink/75">
                    {isKk ? "Статус" : "Статус"}
                  </label>
                  <select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value as TaskStatus)}
                    className="w-full border border-ink/20 rounded px-3 py-1.5 bg-paper text-ink"
                  >
                    <option value="not_started">{isKk ? "Басталмаған" : "Не начато"}</option>
                    <option value="in_progress">{isKk ? "Орындалуда" : "В процессе"}</option>
                    <option value="done">{isKk ? "Дайын" : "Завершено"}</option>
                    <option value="blocked">{isKk ? "Бұғатталған" : "Заблокировано"}</option>
                  </select>
                </div>

                <div>
                  <label className="block font-medium mb-1 text-ink/75">
                    {isKk ? "Байланысты жұмыс (Predecessor)" : "Предшественник (Зависит от)"}
                  </label>
                  <select
                    value={formDepends}
                    onChange={(e) => setFormDepends(e.target.value)}
                    className="w-full border border-ink/20 rounded px-3 py-1.5 bg-paper text-ink"
                  >
                    <option value="">{isKk ? "— Байланыссыз —" : "— Без зависимости —"}</option>
                    {schedule
                      .filter((s) => !editingTask || s.id !== editingTask.id)
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.title} ({s.start} → {s.finish})
                        </option>
                      ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-ink/10">
                {editingTask ? (
                  <button
                    type="button"
                    onClick={() => handleDeleteTask(editingTask.id)}
                    className="text-red-600 hover:text-red-700 underline text-xs font-medium"
                  >
                    {isKk ? "Өшіру" : "Удалить работу"}
                  </button>
                ) : (
                  <div />
                )}

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-3 py-1.5 border border-ink/20 rounded hover:bg-mist transition-colors"
                  >
                    {isKk ? "Бас тарту" : "Отмена"}
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-4 py-1.5 bg-pine text-paper font-semibold rounded hover:bg-pine/90 transition-colors disabled:opacity-50"
                  >
                    {saving
                      ? isKk ? "Сақталуда..." : "Сохранение..."
                      : isKk ? "Сақтау" : "Сохранить"}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
