import { describe, expect, it } from "vitest";
import {
  buildFeatures,
  featureOn,
  features,
  menuTabVisible,
  objectMenus,
  objectUsesPilotLayout,
  ORG_FEATURE_KEYS,
  PILOT_MAIN_TABS,
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

  it("keeps pilot tabs when features are enabled", () => {
    expect(objectUsesPilotLayout(null, { demo: false })).toBe(true);
    expect(objectUsesPilotLayout({}, { demo: false })).toBe(true);
    expect(objectUsesPilotLayout({ meetings: true }, { demo: false })).toBe(true);
    expect(objectUsesPilotLayout({}, { demo: true })).toBe(false);
    const menus = objectMenus({ meetings: true, rfi: true }, { demo: false });
    expect(menus.pilot).toBe(true);
    expect(menus.main).toEqual([...PILOT_MAIN_TABS]);
    expect(menus.main).toContain("today");
    expect(menus.main).toContain("procurement");
    expect(menus.more).toContain("meet");
    expect(menus.more).toContain("rfi");
    expect(menus.more).not.toContain("draw");
    expect(menus.more).not.toContain("gantt");
    const drawings = objectMenus({ drawings: true }, { demo: false });
    expect(drawings.main).not.toContain("draw");
    expect(drawings.more).toContain("draw");
    expect(drawings.main).toContain("today");
    expect(drawings.main).toContain("procurement");
    expect(objectMenus({}, { demo: true }).pilot).toBe(false);
    expect(objectMenus({}, { demo: true }).main).not.toContain("today");
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
