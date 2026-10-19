import { afterEach, describe, expect, it } from "vitest";
import { classifyAnchor, isNativeApp, safeFilename, saveBlobDownload, wantsNativeCamera } from "./native";

afterEach(() => {
  delete (window as Window & { Capacitor?: unknown }).Capacitor;
});

describe("native shell detection", () => {
  it("stays off in a normal browser", () => {
    expect(isNativeApp()).toBe(false);
  });

  it("turns on only when the Capacitor bridge says the page is native", () => {
    (window as Window & { Capacitor?: unknown }).Capacitor = { isNativePlatform: () => false };
    expect(isNativeApp()).toBe(false);
    (window as Window & { Capacitor?: unknown }).Capacitor = { isNativePlatform: () => true };
    expect(isNativeApp()).toBe(true);
  });

  it("does not write a file from the browser", async () => {
    await expect(saveBlobDownload("sheet.xlsx", new Blob(["x"]))).resolves.toBe(false);
  });
});

describe("native link and camera routing", () => {
  const origin = "https://app.anyq.example";

  it("keeps same-origin navigation inside the app", () => {
    expect(classifyAnchor(`${origin}/ru/site`, origin, null)).toEqual({ type: "ignore" });
  });

  it("sends WhatsApp links to the share sheet", () => {
    expect(classifyAnchor("https://wa.me/?text=Hello", origin, null)).toEqual({
      type: "whatsapp",
      text: "Hello",
      href: "https://wa.me/?text=Hello",
    });
  });

  it("opens other websites outside the shell", () => {
    expect(classifyAnchor("https://example.com/privacy", origin, null)).toEqual({
      type: "external",
      href: "https://example.com/privacy",
    });
  });

  it("treats a download attribute as a file save", () => {
    expect(classifyAnchor("blob:https://app.anyq.example/1", origin, "comparison.xlsx")).toEqual({
      type: "download",
      filename: "comparison.xlsx",
      href: "blob:https://app.anyq.example/1",
    });
  });

  it("uses the camera for photos and leaves spreadsheets on the file input", () => {
    expect(wantsNativeCamera("image/*", "environment")).toBe(true);
    expect(wantsNativeCamera("image/jpeg,image/png,image/webp", null)).toBe(true);
    expect(wantsNativeCamera(".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", null)).toBe(false);
    expect(wantsNativeCamera("application/pdf", null)).toBe(false);
  });

  it("strips path pieces from a download name", () => {
    expect(safeFilename("../KS-2/act.xlsx")).toBe("__KS-2_act.xlsx");
    expect(safeFilename("   ")).toBe("download");
  });
});
