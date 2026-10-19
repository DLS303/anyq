import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { isCacheableStatic, isPrivateApiRequest } from "./pwa";

describe("service worker boundaries", () => {
  it("treats API and authenticated reads as private", () => {
    expect(isPrivateApiRequest("/v1/procurement/requests")).toBe(true);
    expect(isPrivateApiRequest("/uploads/photo.jpg")).toBe(true);
    expect(isPrivateApiRequest("/health")).toBe(true);
    expect(isPrivateApiRequest("/api/session")).toBe(true);
    expect(isPrivateApiRequest("/ru/site", "POST")).toBe(true);
    expect(isPrivateApiRequest("/icons/icon-192.png", "GET", "Bearer token")).toBe(true);
    expect(isPrivateApiRequest("/ru/site")).toBe(false);
  });

  it("caches only public static files", () => {
    expect(isCacheableStatic("/_next/static/chunks/app.js")).toBe(true);
    expect(isCacheableStatic("/icons/icon-512.png")).toBe(true);
    expect(isCacheableStatic("/favicon.svg")).toBe(true);
    expect(isCacheableStatic("/manifest.webmanifest")).toBe(true);
    expect(isCacheableStatic("/ru")).toBe(false);
    expect(isCacheableStatic("/v1/modules")).toBe(false);
  });

  it("keeps the same exclusions in the service worker", () => {
    const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
    const source = readFileSync(resolve(root, "public/sw.js"), "utf8");
    for (const marker of ["/v1/", "/uploads/", "/health", "/api/", "authorization", "/_next/static/"]) {
      expect(source).toContain(marker);
    }
  });
});
