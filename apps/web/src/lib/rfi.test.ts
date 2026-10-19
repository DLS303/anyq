import { describe, expect, it } from "vitest";
import { canTransition, isOverdue, whatsAppHref } from "./rfi";

describe("rfi share link", () => {
  it("puts the public reply page in the WhatsApp text", () => {
    const token = "tok_only_secret_value";
    const href = whatsAppHref("https://app.example/", "ru", token);
    const text = new URL(href).searchParams.get("text");
    expect(text).toBe(`https://app.example/ru/r/rfi/${token}`);
    expect(href.startsWith("https://wa.me/?text=")).toBe(true);
    expect(text).not.toContain("+7700");
    expect(text).not.toContain(" ");
  });
});

describe("rfi status", () => {
  it("rejects a move that is not allowed", () => {
    expect(canTransition("open", "answered")).toBe(true);
    expect(canTransition("open", "closed")).toBe(true);
    expect(canTransition("answered", "closed")).toBe(true);
    expect(canTransition("answered", "open")).toBe(false);
    expect(canTransition("closed", "open")).toBe(false);
    expect(canTransition("closed", "answered")).toBe(false);
    expect(canTransition("open", "open")).toBe(false);
  });

  it("marks an open question overdue only after the due date", () => {
    expect(isOverdue("open", "2026-10-01", "2026-10-19")).toBe(true);
    expect(isOverdue("open", "2026-10-19", "2026-10-19")).toBe(false);
    expect(isOverdue("answered", "2026-10-01", "2026-10-19")).toBe(false);
    expect(isOverdue("open", "", "2026-10-19")).toBe(false);
  });
});
