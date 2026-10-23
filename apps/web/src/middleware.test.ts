import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

async function respond(path: string, flag: string) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_REGISTRATION_ENABLED", flag);
  const { middleware } = await import("./middleware");
  return middleware(new NextRequest(new URL(path, "http://localhost:3000")));
}

describe("register routes", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("sends /register and register mode to login when sign-up is off", async () => {
    const root = await respond("/register", "");
    expect(root.status).toBe(307);
    expect(root.headers.get("location")).toBe("http://localhost:3000/ru/login");

    const localized = await respond("/kk/register", "0");
    expect(localized.headers.get("location")).toBe("http://localhost:3000/kk/login");

    const query = await respond("/ru/login?mode=register", "false");
    expect(query.headers.get("location")).toBe("http://localhost:3000/ru/login");

    const login = await respond("/ru/login", "0");
    expect(login.headers.get("location")).toBeNull();
    expect(login.status).toBe(200);
  });

  it("leaves /register in place when sign-up is on", async () => {
    const open = await respond("/ru/register", "1");
    expect(open.headers.get("location")).toBeNull();
    expect(open.status).toBe(200);

    const mode = await respond("/ru/login?mode=register", "1");
    expect(mode.headers.get("location")).toBeNull();
  });
});
