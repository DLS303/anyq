import { describe, expect, it } from "vitest";
import {
  applyUploadedRevision,
  drawingCreatePath,
  drawingFilePath,
  drawingSheetsPath,
  gateStatus,
  hasNewerVersion,
} from "./drawings";

const revA = { id: "a", rev: "A", file_id: "f1", is_current: true, row_version: 1 };
const revB = { id: "b", rev: "B", file_id: "f2", is_current: true, row_version: 1 };

describe("drawing revisions", () => {
  it("archives the previous revision when a new one is uploaded", () => {
    const next = applyUploadedRevision([revA], revB);
    expect(next).not.toBe(409);
    if (next === 409) return;
    expect(next.find((item) => item.rev === "A")?.is_current).toBe(false);
    expect(next.find((item) => item.rev === "B")?.is_current).toBe(true);
    expect(next.filter((item) => item.is_current)).toHaveLength(1);
  });

  it("rejects a repeated revision with 409", () => {
    expect(applyUploadedRevision([revA], { ...revA, id: "again" })).toBe(409);
    expect(gateStatus(409)).toBe("conflict");
  });

  it("hides a foreign company response", () => {
    expect(gateStatus(404)).toBe("hidden");
    expect(hasNewerVersion([{ ...revA, is_current: false }, revB], "A")).toBe(true);
    expect(hasNewerVersion([revA], "A")).toBe(false);
  });

  it("does not put a project id in the query string", () => {
    const other = "prj-other-company";
    expect(drawingSheetsPath("prj-home")).not.toContain("pid=");
    expect(drawingSheetsPath("prj-home")).not.toContain(other);
    expect(drawingCreatePath("prj-home")).toBe("/v1/site/projects/prj-home/drawings");
    expect(drawingFilePath("sheet-1", "A")).not.toContain("pid=");
    expect(drawingFilePath("sheet-1", "A")).toContain("rev=A");
  });
});
