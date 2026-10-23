import { describe, expect, it } from "vitest";
import { publicRegistrationOpen, registerLink, registrationEnabled } from "./registration";

describe("NEXT_PUBLIC_REGISTRATION_ENABLED", () => {
  it("stays off unless the value is 1, true, yes, or on", () => {
    expect(registrationEnabled(undefined)).toBe(false);
    expect(registrationEnabled("")).toBe(false);
    expect(registrationEnabled("0")).toBe(false);
    expect(registrationEnabled("false")).toBe(false);
    expect(registrationEnabled("1")).toBe(true);
    expect(registrationEnabled(" TRUE ")).toBe(true);
    expect(registrationEnabled("yes")).toBe(true);
    expect(registrationEnabled("on")).toBe(true);
  });

  it("hides the sign-up link when registration or the pilot screen is off", () => {
    expect(publicRegistrationOpen({ enabled: false, pilot: false })).toBe(false);
    expect(registerLink("ru", { enabled: false, pilot: false })).toBeNull();
    expect(registerLink("ru", { enabled: true, pilot: true })).toBeNull();
    expect(registerLink("kk", { enabled: true, pilot: false })).toBe("/kk/login?mode=register");
  });
});
