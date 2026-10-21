"use client";

import { createContext, useContext } from "react";
import type { Msg } from "@/i18n/messages";

const Ctx = createContext<Msg | null>(null);

export function I18nProvider({ messages, children }: { messages: Msg; children: React.ReactNode }) {
  return <Ctx.Provider value={messages}>{children}</Ctx.Provider>;
}

export function useMessages() {
  const value = useContext(Ctx);
  if (!value) throw new Error("I18nProvider missing");
  return value;
}
