/**
 * Release visibility. Demo mode reveals illustrations and the land marketplace.
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
  land: DEMO_MODE,
  controlPanel: DEMO_MODE,
} as const;

/** Public sign-up. Off until NEXT_PUBLIC_REGISTRATION_ENABLED=1. */
export const REGISTRATION_ENABLED = process.env.NEXT_PUBLIC_REGISTRATION_ENABLED === "1";

export const DEMO_ONLY_TABS = ["sub", "draw", "ks"] as const;
