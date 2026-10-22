import { describe, expect, it } from "vitest";
import {
  DEMO_BANNER_TEXT,
  DEMO_EMAIL_ERROR,
  DEMO_PHONE_STUB_CODE,
  DEMO_PHONE_STUB_TEXT,
  SMS_LATER,
  demoContactError,
  detectContact,
} from "./signupContact";

describe("signup contact", () => {
  it("detects a Kazakh phone and a lowercased email", () => {
    expect(detectContact("8 701 111 22 33")).toEqual({ channel: "phone", value: "+77011112233" });
    expect(detectContact("7011112233")).toEqual({ channel: "phone", value: "+77011112233" });
    expect(detectContact("User@Example.com")).toEqual({ channel: "email", value: "user@example.com" });
  });

  it("rejects empty and invalid input", () => {
    expect(detectContact("  ").channel).toBe("invalid");
    expect(detectContact("123").channel).toBe("invalid");
    expect(detectContact("not-an-email").channel).toBe("invalid");
  });

  it("allows a demo phone and blocks a non-demo email", () => {
    const phone = detectContact("+77011112233");
    const foreign = detectContact("a@example.com");
    const demo = detectContact("a@demo.superapp");
    expect(demoContactError(phone, true)).toBeNull();
    expect(demoContactError(foreign, true)).toBe(DEMO_EMAIL_ERROR);
    expect(demoContactError(demo, true)).toBeNull();
    expect(demoContactError(phone, false)).toBeNull();
    expect(DEMO_PHONE_STUB_CODE).toBe("000000");
    expect(DEMO_PHONE_STUB_TEXT).toContain("Демо:");
    expect(DEMO_PHONE_STUB_TEXT).toContain(DEMO_PHONE_STUB_CODE);
  });

  it("keeps the banner and SMS copy exact", () => {
    expect(DEMO_BANNER_TEXT).toBe(
      "Демо-версия: данные могут быть сброшены, не вводите настоящие персональные данные",
    );
    expect(SMS_LATER).toBe("Подтверждение по SMS появится позже");
  });
});
