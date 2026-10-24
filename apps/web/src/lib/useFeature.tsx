"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchCompanyFeatures } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  buildFeatures,
  featureOn,
  type CompanyFlags,
  type OrgFeatureKey,
} from "@/lib/features";

type FeatureState = {
  flags: CompanyFlags | null;
  reload: () => void;
};

const FeatureCtx = createContext<FeatureState | null>(null);

export const FEATURES_REFRESH = "anyq:features";

export function FeatureProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const [flags, setFlags] = useState<CompanyFlags | null>(null);

  const reload = useCallback(() => {
    if (!token) {
      setFlags(null);
      return;
    }
    fetchCompanyFeatures()
      .then((rows) => {
        const next: CompanyFlags = {};
        for (const row of rows) next[row.key as OrgFeatureKey] = Boolean(row.enabled);
        setFlags(next);
      })
      .catch(() => setFlags(null));
  }, [token]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const onRefresh = () => reload();
    window.addEventListener(FEATURES_REFRESH, onRefresh);
    return () => window.removeEventListener(FEATURES_REFRESH, onRefresh);
  }, [reload]);

  const value = useMemo(() => ({ flags, reload }), [flags, reload]);
  return <FeatureCtx.Provider value={value}>{children}</FeatureCtx.Provider>;
}

export function useFeature(key: OrgFeatureKey) {
  const ctx = useContext(FeatureCtx);
  return featureOn(key, ctx?.flags);
}

export function useProjectFeatures(projectFlags?: CompanyFlags | null) {
  const drawings = useFeature("drawings");
  const punchPhotos = useFeature("punch_photos");
  const checklists = useFeature("checklists");
  const rfi = useFeature("rfi");
  const submittals = useFeature("submittals");
  const submittalsProcurement = useFeature("submittals_procurement");
  const changes = useFeature("changes");
  const subcontracts = useFeature("subcontracts");
  const gantt = useFeature("gantt");
  const meetings = useFeature("meetings");
  const offline = useFeature("offline");
  const ksActs = useFeature("ks_acts");
  return useMemo(() => {
    if (projectFlags) return buildFeatures(projectFlags);
    return buildFeatures({
      drawings,
      punch_photos: punchPhotos,
      checklists,
      rfi,
      submittals,
      submittals_procurement: submittalsProcurement,
      changes,
      subcontracts,
      gantt,
      meetings,
      offline,
      ks_acts: ksActs,
    });
  }, [
    projectFlags,
    drawings,
    punchPhotos,
    checklists,
    rfi,
    submittals,
    submittalsProcurement,
    changes,
    subcontracts,
    gantt,
    meetings,
    offline,
    ksActs,
  ]);
}
