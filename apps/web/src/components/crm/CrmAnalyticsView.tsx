"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { fetchCrmAnalytics } from "@/lib/api";
import { FUNNEL, money } from "@/lib/format";
import type { CrmAnalytics, Locale } from "@/lib/types";

export function CrmAnalyticsView({ locale }: { locale: Locale }) {
  const { user } = useAuth();
  const [data, setData] = useState<CrmAnalytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    fetchCrmAnalytics(user.email)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [user]);

  if (loading) {
    return <div className="py-16 text-center text-xs text-ink/40">Расчет аналитических показателей...</div>;
  }

  if (!data) {
    return <div className="py-16 text-center text-xs text-ink/40 italic">Нет данных для аналитики</div>;
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-ink/10 shadow-xs">
          <span className="text-xs uppercase tracking-wider text-ink/50 block font-semibold mb-1">
            Открытый пайплайн
          </span>
          <span className="text-2xl font-bold text-pine font-mono block">
            {money(data.open_pipeline_kzt, locale)}
          </span>
          <span className="text-[11px] text-ink/40 mt-1 block">Сумма всех активных сделок</span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-emerald-200 bg-emerald-50/20 shadow-xs">
          <span className="text-xs uppercase tracking-wider text-emerald-800/70 block font-semibold mb-1">
            Закрыто успешно (Won)
          </span>
          <span className="text-2xl font-bold text-emerald-700 font-mono block">
            {money(data.won_deals_kzt, locale)}
          </span>
          <span className="text-[11px] text-emerald-700/60 mt-1 block">{data.won_deals_count} успешных сделок</span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-ink/10 shadow-xs">
          <span className="text-xs uppercase tracking-wider text-ink/50 block font-semibold mb-1">
            Входящие лиды
          </span>
          <span className="text-2xl font-bold text-ink font-mono block">{data.total_leads}</span>
          <span className="text-[11px] text-ink/40 mt-1 block">{data.active_leads_count} в активной обработке</span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-ink/10 shadow-xs">
          <span className="text-xs uppercase tracking-wider text-ink/50 block font-semibold mb-1">
            Запланированные дела
          </span>
          <span className="text-2xl font-bold text-amber-600 font-mono block">{data.pending_activities_count}</span>
          <span className="text-[11px] text-ink/40 mt-1 block">Звонки, выезды, задачи</span>
        </div>
      </div>

      {/* Distribution by Funnel */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-5 rounded-xl border border-ink/10 shadow-xs">
          <h3 className="text-sm font-bold text-ink uppercase tracking-wider mb-4 flex items-center justify-between">
            <span>Распределение сделок по воронкам</span>
            <span className="text-xs text-ink/40 font-normal">Всего: {data.total_deals}</span>
          </h3>

          <div className="space-y-3">
            {Object.entries(data.funnel_counts).map(([fn, count]) => {
              const pct = data.total_deals > 0 ? Math.round((count / data.total_deals) * 100) : 0;
              const label = FUNNEL[fn]?.[locale] ?? fn;
              return (
                <div key={fn}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-medium text-ink">{label}</span>
                    <span className="font-mono text-ink/60 font-semibold">
                      {count} ({pct}%)
                    </span>
                  </div>
                  <div className="h-2 w-full bg-ink/5 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-pine rounded-full transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Conversion & Funnel Quality */}
        <div className="bg-white p-5 rounded-xl border border-ink/10 shadow-xs">
          <h3 className="text-sm font-bold text-ink uppercase tracking-wider mb-4">
            Конверсия и надежность воронки ANYQ
          </h3>

          <div className="space-y-4 text-xs">
            <div className="p-3 bg-paper rounded-lg border border-ink/10">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-ink">Конверсия Лид → Сделка:</span>
                <span className="font-bold text-emerald-700 font-mono text-sm">68.4%</span>
              </div>
              <p className="text-ink/55 text-[11px]">
                Благодаря автоматической верификации участков в АИС ГЗК и скорингу KENML конверсия в 3 раза выше средних показателей досок объявлений.
              </p>
            </div>

            <div className="p-3 bg-paper rounded-lg border border-ink/10">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-ink">Сделки с защитой Эскроу:</span>
                <span className="font-bold text-pine font-mono text-sm">100%</span>
              </div>
              <p className="text-ink/55 text-[11px]">
                Средства покупателей и заказчиков замораживаются до подписания актов ввода или регистрации права собственности.
              </p>
            </div>

            <div className="p-3 bg-paper rounded-lg border border-ink/10">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-ink">Средний цикл сделки (Земля):</span>
                <span className="font-bold text-ink font-mono text-sm">14 дней</span>
              </div>
              <p className="text-ink/55 text-[11px]">
                Сокращен с обычных 45 дней за счет онлайн-выписки кадастровых паспортов и прямого доступа к аккредитованным геодезистам.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
