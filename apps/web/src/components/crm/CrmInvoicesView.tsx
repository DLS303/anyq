"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { fetchInvoices, payInvoice } from "@/lib/api";
import { INVOICE_STATUS, money } from "@/lib/format";
import type { CrmInvoice, Locale } from "@/lib/types";

export function CrmInvoicesView({
  locale,
  onSelectDealId,
}: {
  locale: Locale;
  onSelectDealId: (dealId: string) => void;
}) {
  const { user } = useAuth();
  const [invoices, setInvoices] = useState<CrmInvoice[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    if (!user) return;
    setLoading(true);
    fetchInvoices(user.email)
      .then(setInvoices)
      .catch(() => setInvoices([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function handlePay(id: string) {
    if (!user) return;
    try {
      await payInvoice(user.email, id);
      load();
      alert("Счет успешно оплачен через Kaspi Pay / Эскроу ANYQ!");
    } catch (e) {
      alert((e as Error).message);
    }
  }

  const totalPaid = invoices.filter((i) => i.status === "paid").reduce((s, i) => s + i.amount_kzt, 0);
  const totalPending = invoices.filter((i) => i.status !== "paid").reduce((s, i) => s + i.amount_kzt, 0);

  return (
    <div className="space-y-4">
      {/* Top Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-xl border border-ink/10 shadow-xs">
          <span className="text-xs text-ink/50 block mb-1">Всего счетов</span>
          <span className="text-2xl font-bold text-ink">{invoices.length}</span>
        </div>
        <div className="bg-white p-4 rounded-xl border border-emerald-200 bg-emerald-50/30 shadow-xs">
          <span className="text-xs text-emerald-800/70 block mb-1">Оплачено (Эскроу ANYQ)</span>
          <span className="text-2xl font-bold text-emerald-700 font-mono">{money(totalPaid, locale)}</span>
        </div>
        <div className="bg-white p-4 rounded-xl border border-amber-200 bg-amber-50/30 shadow-xs">
          <span className="text-xs text-amber-800/70 block mb-1">Ожидает оплаты / В пайплайне</span>
          <span className="text-2xl font-bold text-amber-700 font-mono">{money(totalPending, locale)}</span>
        </div>
      </div>

      {/* Invoices Table */}
      <div className="bg-white rounded-xl border border-ink/10 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-paper text-ink/60 border-b border-ink/10 uppercase tracking-wider font-semibold">
              <tr>
                <th className="py-3 px-4">Номер счета</th>
                <th className="py-3 px-3">Назначение</th>
                <th className="py-3 px-3">Сумма</th>
                <th className="py-3 px-3">Статус</th>
                <th className="py-3 px-3">Плательщик</th>
                <th className="py-3 px-3">Срок / Дата</th>
                <th className="py-3 px-3">Эскроу</th>
                <th className="py-3 px-4 text-right">Действие</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/5">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-ink/40">Загрузка счетов...</td>
                </tr>
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-ink/40 italic">Счетов пока нет</td>
                </tr>
              ) : (
                invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-pine/5 transition-colors">
                    <td className="py-3 px-4 font-mono font-bold text-ink">
                      {inv.number}
                    </td>
                    <td className="py-3 px-3 font-medium text-ink">
                      <div>{inv.title}</div>
                      {inv.deal_id && (
                        <button
                          type="button"
                          onClick={() => onSelectDealId(inv.deal_id)}
                          className="text-[11px] text-pine underline block mt-0.5"
                        >
                          Сделка #{inv.deal_id} →
                        </button>
                      )}
                    </td>
                    <td className="py-3 px-3 font-bold font-mono text-sm text-pine">
                      {money(inv.amount_kzt, locale)}
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          INVOICE_STATUS[inv.status]?.color ?? "bg-gray-100"
                        }`}
                      >
                        {INVOICE_STATUS[inv.status]?.ru ?? inv.status}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-ink">
                      <div className="font-medium">{inv.payer_name}</div>
                      {inv.payer_iin_bin && (
                        <div className="text-[11px] text-ink/45 font-mono">БИН: {inv.payer_iin_bin}</div>
                      )}
                    </td>
                    <td className="py-3 px-3 text-ink/55 font-mono text-[11px]">
                      {inv.due_date || inv.created_at.slice(0, 10)}
                    </td>
                    <td className="py-3 px-3">
                      {inv.escrow_enabled ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                          🛡️ Эскроу ANYQ
                        </span>
                      ) : (
                        <span className="text-[11px] text-ink/45">Прямой</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {inv.status === "paid" ? (
                        <span className="text-emerald-700 font-semibold text-[11px]">✓ Оплачен</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handlePay(inv.id)}
                          className="px-3 py-1 bg-emerald-600 text-white rounded text-[11px] font-semibold hover:bg-emerald-700 transition-colors shadow-2xs"
                        >
                          💳 Оплатить (Kaspi)
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
    </div>
  );
}
