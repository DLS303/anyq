"use client";

import { useParams } from "next/navigation";
import { ProjectList } from "@/components/site/ProjectList";
import { useAuth } from "@/lib/auth";
import { t } from "@/i18n/messages";
import { PILOT_MODE } from "@/lib/pilot";
import type { Locale } from "@/lib/types";

export default function SiteListPage() {
  const params = useParams<{ locale: string }>();
  const locale = (params.locale as Locale) || "ru";
  const m = t(locale);
  const { user } = useAuth();
  const supervisor = user?.role === "supervisor";

  return (
    <div>
      <h1 className="mb-2 mt-2 text-2xl font-medium tracking-tight sm:text-4xl">
        {supervisor ? m.myObjects : PILOT_MODE ? m.navObjects : m.navSite}
      </h1>
      <p className="mb-6 max-w-2xl text-ink/60">
        {supervisor ? m.myObjectsLead : PILOT_MODE ? m.siteLead : m.siteLeadFull}
      </p>
      <ProjectList locale={locale} />
    </div>
  );
}
