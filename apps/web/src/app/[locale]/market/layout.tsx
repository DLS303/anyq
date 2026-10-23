"use client";

import { useParams } from "next/navigation";
import { MarketShell } from "@/components/market/MarketShell";
import type { Locale } from "@/lib/types";

export default function MarketLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ locale: string }>();
  const locale = (params.locale as Locale) || "ru";
  return <MarketShell locale={locale}>{children}</MarketShell>;
}
