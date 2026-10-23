"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { createRequest } from "@/lib/marketApi";
import {
  lineFromCard,
  readBasket,
  removeBasket,
  supplierIds,
  upsertBasket,
  writeBasket,
  type BasketLine,
  type MarketCardItem,
} from "@/lib/market";
import type { Locale } from "@/lib/types";

type BasketApi = {
  lines: BasketLine[];
  has: (catalogId: string) => boolean;
  add: (item: MarketCardItem) => void;
  remove: (catalogId: string) => void;
};

const BasketContext = createContext<BasketApi | null>(null);

export function useBasket() {
  const value = useContext(BasketContext);
  if (!value) throw new Error("basket");
  return value;
}

export function MarketShell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  const router = useRouter();
  const { user } = useAuth();
  const [lines, setLines] = useState<BasketLine[]>([]);
  const [ready, setReady] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLines(readBasket());
    setReady(true);
  }, []);

  useEffect(() => {
    if (ready) writeBasket(lines);
  }, [lines, ready]);

  const api = useMemo<BasketApi>(
    () => ({
      lines,
      has: (catalogId) => lines.some((line) => line.catalogId === catalogId),
      add: (item) => setLines((current) => upsertBasket(current, lineFromCard(item))),
      remove: (catalogId) => setLines((current) => removeBasket(current, catalogId)),
    }),
    [lines],
  );

  async function send() {
    if (!user) {
      router.push(`/${locale}/login`);
      return;
    }
    if (sending || lines.length === 0) return;
    setSending(true);
    setError("");
    try {
      const created = await createRequest({
        title: "Заявка на материалы",
        supplier_ids: supplierIds(lines),
        lines: lines.map((line) => ({
          catalog_id: line.catalogId,
          name: line.name,
          unit: line.unit,
          qty: line.qty,
          category: line.category,
        })),
      });
      setLines([]);
      router.push(`/${locale}/market/request/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не отправилось");
    } finally {
      setSending(false);
    }
  }

  return (
    <BasketContext.Provider value={api}>
      <div className="mx-auto w-full max-w-3xl overflow-x-hidden px-4 py-4 pb-40">{children}</div>
      {lines.length > 0 ? (
        <div className="fixed inset-x-0 bottom-[4.75rem] z-30 px-3 lg:bottom-4">
          <div className="mx-auto flex max-w-3xl items-center gap-3 rounded-full bg-pine py-2 pl-5 pr-2 text-white shadow-luxury">
            <span className="text-sm font-medium">{lines.length}</span>
            <button
              type="button"
              className="ml-auto inline-flex min-h-14 items-center justify-center rounded-full bg-white px-5 text-base font-semibold text-pine disabled:opacity-60"
              onClick={send}
              disabled={sending}
            >
              Отправить поставщикам
            </button>
          </div>
          {error ? <p className="mx-auto mt-2 max-w-3xl text-center text-sm text-red-700">{error}</p> : null}
        </div>
      ) : null}
    </BasketContext.Provider>
  );
}
