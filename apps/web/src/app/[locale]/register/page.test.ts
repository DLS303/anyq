import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`REDIRECT ${url}`);
  },
}));

vi.mock("@/lib/registration", () => ({
  REGISTRATION_ENABLED: false,
}));

import RegisterPage from "./page";

describe("/register", () => {
  it("sends the visitor to login when registration is off", async () => {
    await expect(RegisterPage({ params: Promise.resolve({ locale: "ru" }) })).rejects.toThrow("REDIRECT /ru/login");
    await expect(RegisterPage({ params: Promise.resolve({ locale: "kk" }) })).rejects.toThrow("REDIRECT /kk/login");
  });
});
