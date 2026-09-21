"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

const KEY = "superapp_compare";
const MAX = 3;

type Ctx = {
  ids: string[];
  toggle: (id: string) => void;
  has: (id: string) => boolean;
  clear: () => void;
};

const CompareCtx = createContext<Ctx | null>(null);

export function CompareProvider({ children }: { children: React.ReactNode }) {
  const [ids, setIds] = useState<string[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setIds(JSON.parse(raw) as string[]);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(ids));
  }, [ids]);

  const value = useMemo<Ctx>(
    () => ({
      ids,
      has: (id) => ids.includes(id),
      clear: () => setIds([]),
      toggle: (id) =>
        setIds((cur) => {
          if (cur.includes(id)) return cur.filter((x) => x !== id);
          if (cur.length >= MAX) return cur;
          return [...cur, id];
        }),
    }),
    [ids],
  );

  return <CompareCtx.Provider value={value}>{children}</CompareCtx.Provider>;
}

export function useCompare() {
  const ctx = useContext(CompareCtx);
  if (!ctx) throw new Error("CompareProvider missing");
  return ctx;
}
