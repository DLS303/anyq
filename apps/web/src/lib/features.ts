/**
 * Release visibility. Demo mode reveals illustrations and the land marketplace.
 * A company flag can open the same construction sections when demo mode is off.
 * Hidden screens stay in the codebase for a later version.
 */
export const DEMO_MODE = process.env.NEXT_PUBLIC_ANYQ_DEMO_MODE === "1";

export const ORG_FEATURE_KEYS = [
  "drawings",
  "punch_photos",
  "checklists",
  "rfi",
  "submittals",
  "submittals_procurement",
  "changes",
  "subcontracts",
  "gantt",
  "meetings",
  "offline",
  "ks_acts",
] as const;

export type OrgFeatureKey = (typeof ORG_FEATURE_KEYS)[number];

export type CompanyFlags = Partial<Record<OrgFeatureKey, boolean>>;

const TAB_FEATURE: Partial<Record<string, OrgFeatureKey>> = {
  rfi: "rfi",
  sub: "submittals",
  draw: "drawings",
  gantt: "gantt",
  meet: "meetings",
  ks: "ks_acts",
};

export function featureOn(key: OrgFeatureKey, flags: CompanyFlags | null | undefined, demo = DEMO_MODE) {
  return demo || Boolean(flags?.[key]);
}

export function buildFeatures(flags: CompanyFlags | null | undefined, demo = DEMO_MODE) {
  return {
    demo,
    chess: demo,
    drawings: featureOn("drawings", flags, demo),
    bim3d: demo,
    ksActs: featureOn("ks_acts", flags, demo),
    submittals: featureOn("submittals", flags, demo),
    demoHouse: demo,
    estimateBaseDate: demo,
    land: demo,
    controlPanel: demo,
    homeStage: demo,
    rfi: featureOn("rfi", flags, demo),
    checklists: featureOn("checklists", flags, demo),
    gantt: featureOn("gantt", flags, demo),
    meetings: featureOn("meetings", flags, demo),
    changes: featureOn("changes", flags, demo),
    punchPhotos: featureOn("punch_photos", flags, demo),
    submittalsProcurement: featureOn("submittals_procurement", flags, demo),
    subcontracts: featureOn("subcontracts", flags, demo),
    offline: featureOn("offline", flags, demo),
  };
}

export const features = buildFeatures(null);

export const DEMO_ONLY_TABS = ["sub", "draw"] as const;

export const PILOT_MAIN_TABS = ["today", "punch", "procurement", "money", "qa"] as const;
export const PILOT_MORE_TABS = ["rfi", "gantt", "crew", "meet", "dir", "sub", "draw", "ks"] as const;
export const LEGACY_OBJECT_TABS = [
  "home",
  "daily",
  "rfi",
  "sub",
  "punch",
  "qa",
  "draw",
  "gantt",
  "money",
  "crew",
  "meet",
  "dir",
  "ks",
] as const;

/** Object screen stays on the pilot layout. Demo mode is the full legacy screen. */
export function objectUsesPilotLayout(_flags: CompanyFlags | null | undefined, options?: { demo?: boolean }) {
  const demo = options?.demo ?? DEMO_MODE;
  return !demo;
}

/** Pilot main tabs always stay. Enabled flags only add items to the more menu. */
export function objectMenus(flags: CompanyFlags | null | undefined, options?: { demo?: boolean }) {
  const demo = options?.demo ?? DEMO_MODE;
  if (!objectUsesPilotLayout(flags, { demo })) {
    return { pilot: false, main: [...LEGACY_OBJECT_TABS], more: [] as string[] };
  }
  return {
    pilot: true,
    main: [...PILOT_MAIN_TABS],
    more: PILOT_MORE_TABS.filter((tab) => menuTabVisible(tab, flags, demo)),
  };
}

export function menuTabVisible(tab: string, flags: CompanyFlags | null | undefined, demo = DEMO_MODE) {
  const key = TAB_FEATURE[tab];
  if (!key) return true;
  return featureOn(key, flags, demo);
}
