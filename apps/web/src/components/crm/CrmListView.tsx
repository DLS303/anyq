"use client";

import { useState } from "react";
import { PageNav, useServerPaged } from "@/components/ui/PagedList";
import { fetchDealsPage } from "@/lib/api";
import { FUNNEL, STAGE, money } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";
import { useMessages } from "@/lib/i18n";
import type { Deal, Locale } from "@/lib/types";

export function CrmListView({
  email,
  funnel,
  refreshKey,
  stages,
  locale,
  onSelectDeal,
  onMoveDeal,
}: {
  email: string;
  funnel: string;
  refreshKey: string;
  stages: Record<string, string[]>;
  locale: Locale;
  onSelectDeal: (deal: Deal) => void;
  onMoveDeal: (dealId: string, stage: string) => void;
}) {
  const m = useMessages();
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search, 300);
  const paged = useServerPaged(`${email}:${funnel}:${debounced}:${refreshKey}`, (page, signal) =>
    email
      ? fetchDealsPage(email, page, 24, { funnel, q: debounced || undefined }, signal)
      : Promise.resolve({ items: [] as Deal[], total: 0 }),
  );

  return (
    <div className="bg-white rounded-xl border border-ink/10 shadow-xs overflow-hidden">
      {/* Search Header */}
      <div className="p-3 border-b border-ink/10 bg-paper/30 flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-sm">
          <input
            type="text"
            placeholder="Поиск по названию, клиенту, телефону..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-ink/15 bg-white focus:outline-none focus:border-pine"
          />
          <span className="absolute left-2.5 top-2 text-xs text-ink/40">🔍</span>
        </div>
        <span className="text-xs text-ink/50">Найдено: {paged.total}</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-paper text-ink/60 border-b border-ink/10 uppercase tracking-wider font-semibold">
            <tr>
              <th className="py-3 px-4">Сделка</th>
              <th className="py-3 px-3">Воронка</th>
              <th className="py-3 px-3">Стадия</th>
              <th className="py-3 px-3">Сумма</th>
              <th className="py-3 px-3">Клиент</th>
              <th className="py-3 px-3">Ответственный</th>
              <th className="py-3 px-3">Создана</th>
              <th className="py-3 px-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/5">
            {paged.total === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-ink/40 italic">
                  Сделок не найдено
                </td>
              </tr>
            ) : (
              paged.slice.map((d) => {
                const stageList = stages[d.funnel] ?? [];
                return (
                  <tr
                    key={d.id}
                    onClick={() => onSelectDeal(d)}
                    className="hover:bg-pine/5 cursor-pointer transition-colors"
                  >
                    <td className="py-3 px-4 font-medium text-ink">
                      <div className="font-semibold text-sm hover:text-pine">{d.title}</div>
                      {d.plot_title && <div className="text-[11px] text-ink/50">📍 {d.plot_title}</div>}
                    </td>
                    <td className="py-3 px-3 text-ink/70">
                      {FUNNEL[d.funnel]?.[locale] ?? d.funnel}
                    </td>
                    <td className="py-3 px-3" onClick={(e) => e.stopPropagation()}>
                      <select
                        value={d.stage}
                        onChange={(e) => onMoveDeal(d.id, e.target.value)}
                        className="text-xs font-medium py-1 px-2 rounded border border-ink/15 bg-white"
                      >
                        {stageList.map((st) => (
                          <option key={st} value={st}>
                            {STAGE[st]?.[locale] ?? st}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-3 px-3 font-bold font-mono text-pine">
                      {money(d.amount_kzt, locale)}
                    </td>
                    <td className="py-3 px-3 text-ink">
                      <div className="font-medium">{d.client_name || "—"}</div>
                      {d.client_phone && <div className="text-[11px] text-ink/50">{d.client_phone}</div>}
                    </td>
                    <td className="py-3 px-3 text-ink/70">
                      {d.responsible_name || "Асет Сагинтаев"}
                    </td>
                    <td className="py-3 px-3 text-ink/50 font-mono text-[11px]">
                      {d.created_at.slice(0, 10)}
                    </td>
                    <td className="py-3 px-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => onSelectDeal(d)}
                        className="px-2.5 py-1 text-[11px] bg-paper border border-ink/15 rounded hover:bg-pine hover:text-white transition-colors"
                      >
                        Карточка →
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <div className="px-3 pb-3">
        <PageNav
          page={paged.page}
          pages={paged.pages}
          status={m.pageStatus.replace("{page}", String(paged.page + 1)).replace("{pages}", String(paged.pages))}
          prevLabel={m.pagePrev}
          nextLabel={m.pageNext}
          onPage={paged.setPage}
        />
      </div>
    </div>
  );
}
