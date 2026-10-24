"use client";

import { useCallback, useState } from "react";
import { t } from "@/i18n/messages";
import { ApiError, fetchCompanyFeatures, setCompanyFeature, type CompanyFeatureRecord } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ORG_FEATURE_KEYS, type OrgFeatureKey } from "@/lib/features";
import { useAsync } from "@/lib/useAsync";
import { FEATURES_REFRESH } from "@/lib/useFeature";
import type { Locale } from "@/lib/types";

const COPY: Record<OrgFeatureKey, { title: "featDrawings"; hint: "featDrawingsHint" } | { title: string; hint: string }> = {
  drawings: { title: "featDrawings", hint: "featDrawingsHint" },
  punch_photos: { title: "featPunchPhotos", hint: "featPunchPhotosHint" },
  checklists: { title: "featChecklists", hint: "featChecklistsHint" },
  rfi: { title: "featRfi", hint: "featRfiHint" },
  submittals: { title: "featSubmittals", hint: "featSubmittalsHint" },
  submittals_procurement: { title: "featSubmittalsProcurement", hint: "featSubmittalsProcurementHint" },
  changes: { title: "featChanges", hint: "featChangesHint" },
  subcontracts: { title: "featSubcontracts", hint: "featSubcontractsHint" },
  gantt: { title: "featGantt", hint: "featGanttHint" },
  meetings: { title: "featMeetings", hint: "featMeetingsHint" },
  offline: { title: "featOffline", hint: "featOfflineHint" },
  ks_acts: { title: "featKsActs", hint: "featKsActsHint" },
};

type CopyKey = keyof ReturnType<typeof t>;

export function ObjectFeatures({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const [notice, setNotice] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const query = useAsync((signal) => fetchCompanyFeatures(undefined, signal), [user?.id]);
  const rows = query.data;

  const save = useCallback(
    async (row: CompanyFeatureRecord, enabled: boolean) => {
      if (!owner) return;
      setNotice("");
      setBusyKey(row.key);
      const id = row.id || (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : undefined);
      try {
        await setCompanyFeature({
          key: row.key,
          enabled,
          company_id: row.company_id,
          id: id || undefined,
          row_version: row.row_version,
        });
        setNotice(m.featureSaved);
        window.dispatchEvent(new Event(FEATURES_REFRESH));
        await query.reload();
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          setNotice(m.featureConflict);
          await query.reload();
        } else if (error instanceof ApiError && error.status === 404) {
          setNotice(m.featureMissing);
        } else {
          setNotice(m.featureSaveError);
        }
      } finally {
        setBusyKey("");
      }
    },
    [m.featureConflict, m.featureMissing, m.featureSaveError, m.featureSaved, owner, query],
  );

  if (!user) {
    return <p className="text-sm text-ink/70">{m.navLogin}</p>;
  }
  if (query.loading && !rows) {
    return <p className="text-sm text-ink/70">{m.hubLoading}</p>;
  }
  if (query.status === "error" && !rows) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="grid gap-3">
        <p className="text-sm text-red-700" role="alert">
          {missing ? m.featureMissing : m.hubLoadError}
        </p>
        <button type="button" className="min-h-12 w-fit underline text-sm" onClick={() => query.reload()}>
          {m.hubRetry}
        </button>
      </div>
    );
  }

  const byKey = new Map((rows || []).map((row) => [row.key, row]));

  return (
    <div className="grid gap-4">
      <p className="text-sm text-ink/70">{m.objectFeaturesLead}</p>
      {owner ? null : <p className="text-sm text-ink/70">{m.featureReadOnly}</p>}
      {notice ? (
        <p className="text-sm" role="status">
          {notice}
        </p>
      ) : null}
      <ul className="grid gap-3">
        {ORG_FEATURE_KEYS.map((key) => {
          const row = byKey.get(key);
          const copy = COPY[key];
          const title = m[copy.title as CopyKey];
          const hint = m[copy.hint as CopyKey];
          const on = Boolean(row?.enabled);
          return (
            <li key={key} className="border border-ink/10 bg-white/70 p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium">{title}</p>
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  aria-label={title}
                  disabled={!owner || busyKey === key || !row}
                  onClick={() => row && save(row, !on)}
                  className={`min-h-12 min-w-16 rounded-full px-4 text-sm ${on ? "bg-pine text-paper" : "bg-ink/10 text-ink"} disabled:opacity-50`}
                >
                  {on ? m.modYes : m.modNo}
                </button>
              </div>
              <p className="mt-1 text-sm text-ink/70">{hint}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
