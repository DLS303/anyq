import type { Locale } from "@/lib/types";

type Pack = Record<string, string>;

// Browser builds use the locale pack the server layout already sent.
// The full dictionary stays on the server so app screens do not download it.
export function t(_locale: Locale): Pack {
  const live = (globalThis as { __ANYQ_MESSAGES?: Pack }).__ANYQ_MESSAGES;
  if (!live) throw new Error("I18nProvider missing");
  return live;
}
