import { describe, expect, it } from "vitest";
import { features } from "./features";

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
});
