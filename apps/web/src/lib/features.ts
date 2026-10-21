/**
 * Release visibility. Demo mode reveals illustrations.
 * Hidden screens stay in the codebase for a later version.
 */
export const DEMO_MODE = process.env.NEXT_PUBLIC_ANYQ_DEMO_MODE === "1";

export const features = {
  demo: DEMO_MODE,
  chess: DEMO_MODE,
  drawings: DEMO_MODE,
  bim3d: DEMO_MODE,
  ksActs: DEMO_MODE,
  submittals: DEMO_MODE,
  demoHouse: DEMO_MODE,
  estimateBaseDate: DEMO_MODE,
  controlPanel: DEMO_MODE,
  homeStage: DEMO_MODE,
} as const;

export const DEMO_ONLY_TABS = ["sub", "draw", "ks"] as const;
