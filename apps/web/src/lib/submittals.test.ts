import { describe, expect, it } from "vitest";
import { referrerPolicyFor } from "./features";
import {
  DECIDE_TAPS,
  SEND_TAPS,
  SUBMITTAL_REQUIRED,
  brandAllowed,
  canTransition,
  isOverdue,
  overdueCount,
  priceShown,
} from "./submittals";

describe("material approval rules", () => {
  it("keeps the send action to three required fields and three taps", () => {
    expect(SUBMITTAL_REQUIRED).toEqual(["name", "brand", "file"]);
    expect(SEND_TAPS).toBeLessThanOrEqual(3);
    expect(DECIDE_TAPS).toBeLessThanOrEqual(2);
  });

  it("rejects a status move that is not allowed", () => {
    expect(canTransition("draft", "in_review")).toBe(true);
    expect(canTransition("draft", "withdrawn")).toBe(true);
    expect(canTransition("in_review", "approved")).toBe(true);
    expect(canTransition("in_review", "approved_with_note")).toBe(true);
    expect(canTransition("in_review", "rejected")).toBe(true);
    expect(canTransition("approved", "draft")).toBe(false);
    expect(canTransition("rejected", "approved")).toBe(false);
    expect(canTransition("withdrawn", "in_review")).toBe(false);
  });

  it("counts overdue open materials and hides a price without a file", () => {
    expect(isOverdue("in_review", "2026-10-01", "2026-10-19")).toBe(true);
    expect(isOverdue("approved", "2026-10-01", "2026-10-19")).toBe(false);
    expect(isOverdue("draft", "2026-10-19", "2026-10-19")).toBe(false);
    expect(overdueCount([{ overdue: true }, { overdue: false }, { overdue: true }])).toBe(2);
    expect(priceShown(8900, "file-1")).toBe(true);
    expect(priceShown(8900, null)).toBe(false);
    expect(priceShown(null, "file-1")).toBe(false);
  });

  it("marks a different brand and accepts an allowed analog", () => {
    expect(brandAllowed("ПП-СТ-100-МВ RAL9003", ["ПП-СТ-100-МВ RAL9010"], "ПП-СТ-100-ППС RAL9003")).toBe(false);
    expect(brandAllowed("ПП-СТ-100-МВ RAL9003", ["ПП-СТ-100-МВ RAL9010"], "ПП-СТ-100-МВ RAL9010")).toBe(true);
    expect(brandAllowed("ПП-СТ-100-МВ RAL9003", [], "")).toBe(true);
  });

  it("asks token pages not to send a referrer", () => {
    expect(referrerPolicyFor("/ru/r/material/token")).toBe("no-referrer");
    expect(referrerPolicyFor("/kk/r/rfi/token")).toBe("no-referrer");
    expect(referrerPolicyFor("/ru/site")).toBeNull();
  });
});
