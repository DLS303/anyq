import { describe, expect, it } from "vitest";
import {
  buildFeatures,
  featureOn,
  features,
  menuTabVisible,
  objectUsesPilotLayout,
  ORG_FEATURE_KEYS,
} from "./features";

describe("release visibility", () => {
  it("keeps illustrations behind demo mode", () => {
    const demo = process.env.NEXT_PUBLIC_ANYQ_DEMO_MODE === "1";
    expect(features.demo).toBe(demo);
    expect(features.chess).toBe(demo);
    expect(features.drawings).toBe(demo);
    expect(features.bim3d).toBe(demo);
    expect(features.ksActs).toBe(demo);
    expect(features.submittals).toBe(demo);
    expect(features.demoHouse).toBe(demo);
    expect(features.land).toBe(demo);
  });

  it("opens a section from demo mode or the company flag", () => {
    expect(ORG_FEATURE_KEYS).toContain("drawings");
    expect(featureOn("rfi", {}, false)).toBe(false);
    expect(featureOn("rfi", { rfi: true }, false)).toBe(true);
    expect(featureOn("rfi", {}, true)).toBe(true);
    const flagged = buildFeatures({ drawings: true }, false);
    expect(flagged.drawings).toBe(true);
    expect(flagged.rfi).toBe(false);
    expect(flagged.ksActs).toBe(false);
    expect(buildFeatures(null, true).ksActs).toBe(true);
  });

  it("keeps the pilot object layout when a company flag is on", () => {
    expect(objectUsesPilotLayout(null, { demo: false })).toBe(true);
    expect(objectUsesPilotLayout({}, { demo: false })).toBe(true);
    expect(objectUsesPilotLayout({ meetings: true }, { demo: false })).toBe(true);
    expect(objectUsesPilotLayout({ rfi: true }, { demo: false })).toBe(true);
    expect(objectUsesPilotLayout({}, { demo: true })).toBe(false);
  });

  it("hides a menu item while its flag is off", () => {
    expect(menuTabVisible("rfi", {}, false)).toBe(false);
    expect(menuTabVisible("draw", {}, false)).toBe(false);
    expect(menuTabVisible("rfi", { rfi: true }, false)).toBe(true);
    expect(menuTabVisible("procurement", {}, false)).toBe(true);
    expect(menuTabVisible("today", {}, false)).toBe(true);
    expect(menuTabVisible("money", {}, false)).toBe(true);
    expect(menuTabVisible("ks", { rfi: true }, false)).toBe(false);
    expect(menuTabVisible("ks", {}, true)).toBe(true);
    expect(menuTabVisible("sub", {}, true)).toBe(true);
  });
});
