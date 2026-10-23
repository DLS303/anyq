import { describe, expect, it } from "vitest";
import { guestEntryPath, loginInitialMode, registerHref } from "./registration";

describe("registration gate", () => {
  it("keeps the login screen when sign-up is off", () => {
    expect(loginInitialMode("register", false, false)).toBe("login");
    expect(loginInitialMode(undefined, false, false)).toBe("login");
    expect(loginInitialMode("login", false, true)).toBe("login");
    expect(loginInitialMode("register", true, true)).toBe("login");
  });

  it("opens the register screen only when the flag is on", () => {
    expect(loginInitialMode(undefined, false, true)).toBe("register");
    expect(loginInitialMode("register", false, true)).toBe("register");
  });

  it("points register links at login when sign-up is off", () => {
    expect(registerHref("ru", false)).toBe("/ru/login");
    expect(registerHref("kk", false)).toBe("/kk/login");
    expect(guestEntryPath(false, false)).toBe("/login");
    expect(guestEntryPath(true, true)).toBe("/login");
  });

  it("keeps register links when sign-up is on", () => {
    expect(registerHref("ru", true)).toBe("/ru/login?mode=register");
    expect(guestEntryPath(false, true)).toBe("/login?mode=register");
  });
});
