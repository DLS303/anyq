"use client";

import dynamic from "next/dynamic";
import type { Locale } from "@/lib/types";

const SiteStage = dynamic(() => import("./SiteStage").then((m) => m.SiteStage), {
  ssr: false,
  loading: () => (
    <div
      className="relative ml-[calc(50%-50vw)] mr-[calc(50%-50vw)] h-[250vh] w-screen bg-[#101726]"
      aria-hidden
    />
  ),
});

export function HomeStage({ locale }: { locale: Locale }) {
  return <SiteStage locale={locale} />;
}
