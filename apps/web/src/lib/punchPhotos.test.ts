import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  gateResult,
  isOverdue,
  migratePunchStatus,
  punchListPath,
  punchRequest,
  transitionFailure,
} from "./punchPhotos";

describe("punch photo rules", () => {
  it("migrates legacy statuses", () => {
    expect(migratePunchStatus("ready")).toBe("fixed");
    expect(migratePunchStatus("closed")).toBe("accepted");
    expect(migratePunchStatus("open")).toBe("open");
  });

  it("rejects an illegal status move with 409 and a wrong role with 403", () => {
    expect(transitionFailure(["member"], "open", "accepted", true)).toBe(409);
    expect(transitionFailure(["member"], "open", "fixed", false)).toBe(409);
    expect(transitionFailure(["member"], "open", "fixed", true)).toBeNull();
    expect(transitionFailure(["member"], "fixed", "accepted", true)).toBe(403);
    expect(transitionFailure(["author"], "fixed", "accepted", true)).toBeNull();
    expect(transitionFailure(["supervisor"], "fixed", "returned", true)).toBeNull();
    expect(transitionFailure(["author"], "accepted", "open", true)).toBe(409);
  });

  it("marks a past due date in red only while the item is not accepted", () => {
    expect(isOverdue("2026-10-01", "open", "2026-10-19")).toBe(true);
    expect(isOverdue("2026-10-20", "open", "2026-10-19")).toBe(false);
    expect(isOverdue("2026-10-01", "accepted", "2026-10-19")).toBe(false);
  });

  it("keeps a query project id out of the list path", () => {
    expect(punchListPath("project-a", { pid: "project-b", status: "open", overdue: true })).toBe(
      "/v1/site/projects/project-a/punch-items?status=open&overdue=1",
    );
  });

  it("treats a foreign company as missing on read, write, file, and link", async () => {
    const paths = [
      ["/v1/site/projects/a/punch-items", "GET"],
      ["/v1/site/projects/a/punch-items", "POST"],
      ["/v1/site/projects/a/punch-items/item/files/file", "GET"],
      ["/v1/site/projects/a/punch-items/item/link", "GET"],
    ] as const;
    for (const [path, method] of paths) {
      await expect(punchRequest(path, { method }, async () => ({ status: 404 }))).rejects.toMatchObject({ status: 404 });
    }
    await expect(punchRequest("/status", { method: "POST" }, async () => ({ status: 409 }))).rejects.toMatchObject({ status: 409 });
    expect(gateResult(404)).toBe("missing");
    expect(gateResult(409)).toBe("conflict");
  });

  it("keeps the pilot punch tab and puts the photo tab only in the extra menu", () => {
    const flags = readFileSync(path.resolve(process.cwd(), "src/lib/features.ts"), "utf8");
    const main = flags.match(/export const PILOT_MAIN_TABS = \[([^\]]+)\]/)?.[1] ?? "";
    const more = flags.match(/export const PILOT_MORE_TABS = \[([^\]]+)\]/)?.[1] ?? "";
    expect(main).toContain("punch");
    expect(main).not.toContain("punchPhotos");
    expect(more).toContain("punchPhotos");
    const hub = readFileSync(path.resolve(process.cwd(), "src/components/site/ProjectHub.tsx"), "utf8");
    expect(hub).toContain('status: x.status === "open" ? "ready" : "closed"');
    const screen = readFileSync(path.resolve(process.cwd(), "src/components/site/PunchPhotos.tsx"), "utf8");
    expect(screen).not.toMatch(/[\u0400-\u04FF]/);
  });
});
