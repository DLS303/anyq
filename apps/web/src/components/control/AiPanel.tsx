"use client";

import { useState } from "react";
import {
  Sparkles,
  Zap,
  CheckCircle2,
  ShieldCheck,
  Calculator,
  HardHat,
  Cpu,
  Terminal,
  Play,
  FileCheck2,
} from "lucide-react";

interface AiLog {
  id: string;
  time: string;
  module: string;
  message: string;
  status: "success" | "info" | "warn";
}

const INITIAL_LOGS: AiLog[] = [
  {
    id: "1",
    time: "22:15:02",
    module: "ИИ ANYQ",
    message: "Контур запущен. Смета, журнал площадки и сделки читаются без отдельного подтверждения.",
    status: "info",
  },
  {
    id: "2",
    time: "22:15:18",
    module: "Площадка",
    message: "Корпус Б, Наурыз: готовность каркаса 42%. Журнал работ без замечаний.",
    status: "success",
  },
  {
    id: "3",
    time: "22:16:04",
    module: "Смета",
    message: "Пакетный пересчёт: бетон B25 и арматура A500. Экономия бюджета: 8.4%.",
    status: "success",
  },
  {
    id: "4",
    time: "22:17:30",
    module: "Юристы",
    message: "Журнал корпуса Б: монолит 3 этажа принят, предписания ГАСК отсутствуют.",
    status: "info",
  },
];

function now() {
  return new Date().toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function AiPanel() {
  const [logs, setLogs] = useState<AiLog[]>(INITIAL_LOGS);
  const [isRunning, setIsRunning] = useState(false);
  const [activeTask, setActiveTask] = useState<string | null>(null);

  const runTask = (taskName: string) => {
    setIsRunning(true);
    setActiveTask(taskName);
    setLogs((prev) => [
      {
        id: Date.now().toString(),
        time: now(),
        module: "ИИ",
        message: `Запуск: «${taskName}».`,
        status: "info",
      },
      ...prev,
    ]);

    window.setTimeout(() => {
      setLogs((prev) => [
        {
          id: (Date.now() + 1).toString(),
          time: now(),
          module: "Контур",
          message: `«${taskName}» выполнен. Данные записаны в ANYQ.`,
          status: "success",
        },
        ...prev,
      ]);
      setIsRunning(false);
      setActiveTask(null);
      window.dispatchEvent(
        new CustomEvent("anyq-toast", {
          detail: { message: `ИИ: «${taskName}» завершён` },
        }),
      );
    }, 1800);
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex items-start gap-3 border-b border-slate-100 px-5 py-4">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#2F5B8A] text-white">
          <Zap className="h-5 w-5" />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight text-slate-950">ИИ</h2>
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              В контуре
            </span>
          </div>
          <p className="mt-0.5 text-sm text-slate-500">Смета, журнал площадки и сделки в одном запуске.</p>
        </div>
      </div>

      <div className="space-y-5 p-5">
        <div className="flex items-start gap-3 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-[#2F5B8A]" />
          <p>
            <span className="font-medium text-slate-950">Контур включён.</span> Он сверяет объёмы сметы, журнал
            работ и статус сделки. Это рабочий прогон по данным ANYQ, не внешний чат.
          </p>
        </div>

        <div>
          <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Sparkles className="h-3.5 w-3.5" />
            Запуски
          </h3>
          <div className="grid gap-2 sm:grid-cols-2">
            <TaskButton
              icon={ShieldCheck}
              title="Проверка площадки"
              text="Участки, сети, обременения"
              disabled={isRunning}
              onClick={() => runTask("Проверка площадки и обременений")}
            />
            <TaskButton
              icon={Calculator}
              title="Пересчёт сметы"
              text="Объёмы и прайс по рынку РК"
              disabled={isRunning}
              onClick={() => runTask("Пересчёт сметы")}
            />
            <TaskButton
              icon={FileCheck2}
              title="Акты КС-2 / КС-3"
              text="Журнал монолита и закрытие объёмов"
              disabled={isRunning}
              onClick={() => runTask("Закрытие актов КС-2 и КС-3")}
            />
            <TaskButton
              icon={HardHat}
              title="Подрядчики"
              text="Лицензия и категория перед договором"
              disabled={isRunning}
              onClick={() => runTask("Проверка лицензий подрядчиков")}
            />
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <Terminal className="h-3.5 w-3.5" />
              Журнал
            </h3>
            {isRunning ? (
              <span className="flex items-center gap-1 text-[11px] font-medium text-[#2F5B8A]">
                <Play className="h-3 w-3" />
                {activeTask}
              </span>
            ) : null}
          </div>
          <div className="max-h-56 space-y-2 overflow-y-auto rounded-xl bg-slate-950 p-4 font-mono text-xs text-slate-200">
            {logs.map((log) => (
              <div key={log.id} className="flex items-start gap-2 leading-relaxed">
                <span className="shrink-0 text-slate-500">[{log.time}]</span>
                <span
                  className={`shrink-0 font-semibold ${
                    log.status === "success" ? "text-emerald-400" : log.status === "warn" ? "text-amber-400" : "text-sky-300"
                  }`}
                >
                  [{log.module}]
                </span>
                <span className="text-slate-300">{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50 px-5 py-3">
        <span className="flex items-center gap-1.5 text-xs text-slate-500">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          Пишет в сделки и смету ANYQ
        </span>
        <button
          type="button"
          onClick={() => runTask("Полный цикл: площадка, смета, акты")}
          disabled={isRunning}
          className="inline-flex items-center gap-1.5 rounded-full bg-[#2F5B8A] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
        >
          <Zap className="h-3.5 w-3.5" />
          Полный цикл
        </button>
      </div>
    </div>
  );
}

function TaskButton({
  icon: Icon,
  title,
  text,
  disabled,
  onClick,
}: {
  icon: typeof ShieldCheck;
  title: string;
  text: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 text-left hover:border-[#2F5B8A]/40 disabled:opacity-50"
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-[#2F5B8A]">
        <Icon className="h-4 w-4" />
      </span>
      <span>
        <span className="block text-sm font-medium text-slate-950">{title}</span>
        <span className="mt-0.5 block text-[11px] text-slate-500">{text}</span>
      </span>
    </button>
  );
}
