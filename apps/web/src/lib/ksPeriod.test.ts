import { describe, expect, it } from "vitest";
import { lastMonth } from "./ksPeriod";

describe("lastMonth", () => {
  it("uses the previous calendar month", () => {
    expect(lastMonth(new Date(2026, 9, 24))).toEqual({
      period_from: "2026-09-01",
      period_to: "2026-09-30",
      act_date: "2026-09-30",
    });
  });
});
