"use client";

import { useMemo } from "react";
import Link from "next/link";
import { STAGE, money } from "@/lib/format";
import type { Deal, Locale } from "@/lib/types";

export function CrmKanban({
  stages,
  deals,
  locale,
  onSelectDeal,
  onMoveDeal,
}: {
  stages: string[];
  deals: Deal[];
  locale: Locale;
  onSelectDeal: (deal: Deal) => void;
  onMoveDeal: (dealId: string, targetStage: string) => void;
}) {
  const byStage = useMemo(() => {
    const map: Record<string, Deal[]> = {};
    for (const s of stages) map[s] = [];
    for (const d of deals) {
      if (!map[d.stage]) map[d.stage] = [];
      map[d.stage].push(d);
    }
    return map;
  }, [deals, stages]);

  return (
    <div className="flex gap-3 overflow-x-auto pb-6 pt-2 -mx-4 px-4 snap-x snap-mandatory">
      {stages.map((stage, idx) => {
        const stageDeals = byStage[stage] ?? [];
        const stageTotal = stageDeals.reduce((sum, d) => sum + (d.amount_kzt || 0), 0);
        const meta = STAGE[stage];

        return (
          <div
            key={stage}
            className="min-w-[min(80vw,280px)] w-72 shrink-0 snap-start flex flex-col rounded-xl border border-ink/10 bg-paper/60 backdrop-blur-xs p-3.5 shadow-xs"
          >
            {/* Column Header */}
            <div className="mb-3">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-xs text-ink uppercase tracking-wider">
                  {meta?.[locale] ?? stage}
                </span>
                <span className="grid place-items-center h-5 w-5 rounded-full bg-white text-[11px] font-bold text-ink/70 border border-ink/10 shadow-2xs">
                  {stageDeals.length}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-ink/55 font-mono">
                <span>Объем:</span>
                <span className="font-semibold text-pine">{money(stageTotal, locale)}</span>
              </div>
              {/* Color Accent Bar */}
              <div className={`mt-2 h-1 w-full rounded-full ${meta?.color ? meta.color.split(" ")[0].replace("border-", "bg-") : "bg-pine"}`} />
            </div>

            {/* Cards Container */}
            <div className="flex-1 space-y-2.5 overflow-y-auto max-h-[calc(100vh-280px)] pr-0.5">
              {stageDeals.length === 0 ? (
                <div className="p-4 text-center border border-dashed border-ink/10 rounded-lg text-xs text-ink/40">
                  Нет сделок на этом этапе
                </div>
              ) : (
                stageDeals.map((d) => (
                  <article
                    key={d.id}
                    onClick={() => onSelectDeal(d)}
                    className="group relative cursor-pointer rounded-lg border border-ink/10 bg-white p-3.5 shadow-xs hover:border-pine/50 hover:shadow-md transition-all"
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <span className="text-[10px] font-mono font-medium text-ink/40">#{d.id.slice(-6)}</span>
                      {d.source && (
                        <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-ink/5 text-ink/60 font-medium">
                          {d.source}
                        </span>
                      )}
                    </div>

                    <h4 className="text-sm font-semibold text-ink leading-snug group-hover:text-pine transition-colors">
                      {d.title}
                    </h4>

                    {d.client_name && (
                      <p className="text-xs text-ink/65 mt-1 flex items-center gap-1">
                        <span>👤</span> {d.client_name}
                      </p>
                    )}

                    {d.plot_title && (
                      <p className="text-[11px] text-ink/50 mt-0.5 truncate flex items-center gap-1">
                        <span>📍</span> {d.plot_title}
                      </p>
                    )}

                    <div className="mt-2.5 pt-2 border-t border-ink/5 flex items-center justify-between">
                      <span className="text-xs font-bold text-pine font-mono">
                        {money(d.amount_kzt, locale)}
                      </span>

                      {/* Fast Stage Shift Arrows */}
                      <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100" onClick={(e) => e.stopPropagation()}>
                        {idx > 0 && (
                          <button
                            type="button"
                            title={`Передвинуть на: ${STAGE[stages[idx - 1]]?.[locale] ?? stages[idx - 1]}`}
                            onClick={() => onMoveDeal(d.id, stages[idx - 1])}
                            className="h-6 w-6 rounded border border-ink/15 bg-paper hover:bg-pine hover:text-white grid place-items-center text-xs transition-colors"
                          >
                            ←
                          </button>
                        )}
                        {idx < stages.length - 1 && (
                          <button
                            type="button"
                            title={`Передвинуть на: ${STAGE[stages[idx + 1]]?.[locale] ?? stages[idx + 1]}`}
                            onClick={() => onMoveDeal(d.id, stages[idx + 1])}
                            className="h-6 w-6 rounded border border-ink/15 bg-paper hover:bg-pine hover:text-white grid place-items-center text-xs transition-colors"
                          >
                            →
                          </button>
                        )}
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
