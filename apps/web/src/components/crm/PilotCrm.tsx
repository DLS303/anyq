"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";
import { CrmBoard } from "./CrmBoard";

export function PilotCrm({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();
  const [checked, setChecked] = useState(false);
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    setHasToken(Boolean(localStorage.getItem("superapp_token")));
    setChecked(true);
  }, []);

  if (!checked || (hasToken && !user)) {
    return <p className="text-sm text-ink/60">{m.hubLoading}</p>;
  }

  if (user?.role === "owner" || user?.role === "admin") {
    return <CrmBoard locale={locale} />;
  }

  return (
    <div className="border border-ink/10 bg-white/50 p-6 text-center">
      <p className="text-sm text-ink/70">{m.crmOwnerOnly}</p>
      <Link href={`/${locale}/site`} className="mt-4 inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper">
        {m.crmGoSite}
      </Link>
    </div>
  );
}
