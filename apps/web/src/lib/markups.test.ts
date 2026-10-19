import { describe, expect, it } from "vitest";
import {
  MARKUP_TOOLS,
  arrowShape,
  beginTool,
  cloudShape,
  finishPhoto,
  finishText,
  markupFilePath,
  markupPath,
  markupsForRevision,
  placePoint,
  placementTaps,
  unitPoint,
  unitToPixel,
} from "./markups";

describe("drawing markups", () => {
  it("places each tool in three taps or fewer", () => {
    for (const tool of MARKUP_TOOLS) expect(placementTaps(tool)).toBeLessThanOrEqual(3);

    const arrow = placePoint(placePoint(beginTool("arrow"), { x: 0.2, y: 0.2 }).draft, { x: 0.6, y: 0.7 });
    expect(arrow.ready).toBe("arrow");
    expect(arrow.draft.taps).toBe(0);
    expect(beginTool("arrow").taps + 2).toBeLessThanOrEqual(3);
    expect(arrowShape(arrow.points)).toMatchObject({ x1: 0.2, y1: 0.2, x2: 0.6, y2: 0.7 });

    const cloud = placePoint(placePoint(beginTool("cloud"), { x: 0.1, y: 0.4 }).draft, { x: 0.5, y: 0.8 });
    expect(cloud.ready).toBe("cloud");
    expect(cloudShape(cloud.points)).toMatchObject({ x: 0.1, y: 0.4 });

    const textDraft = placePoint(beginTool("text"), { x: 0.3, y: 0.4 });
    const text = finishText(textDraft.draft, "North note");
    expect(textDraft.draft.taps).toBe(2);
    expect(text.taps).toBeLessThanOrEqual(3);
    expect(text.shape).toMatchObject({ type: "text", x: 0.3, y: 0.4, text: "North note" });

    const photoDraft = placePoint(beginTool("photo"), { x: 0.4, y: 0.5 });
    const photo = finishPhoto(photoDraft.draft, "6f1e2d3c-4b5a-4678-9abc-def012345678");
    expect(photo.taps).toBeLessThanOrEqual(3);
    expect(photo.shape?.type).toBe("photo");
    expect(photo.shape && photo.shape.x + photo.shape.w).toBeLessThanOrEqual(1);
  });

  it("keeps the same sheet point at every zoom", () => {
    const small = { left: 8, top: 12, width: 100, height: 80 };
    const zoomed = { left: 8, top: 12, width: 400, height: 320 };
    const fromSmall = unitPoint(8 + 25, 12 + 20, small);
    const fromZoom = unitPoint(8 + 100, 12 + 80, zoomed);
    expect(fromSmall).toEqual({ x: 0.25, y: 0.25 });
    expect(fromZoom).toEqual(fromSmall);
    expect(unitToPixel(fromSmall, small)).toEqual({ x: 25, y: 20 });
    expect(unitToPixel(fromZoom, zoomed)).toEqual({ x: 100, y: 80 });
    expect(unitPoint(0, 0, small)).toEqual({ x: 0, y: 0 });
    expect(unitPoint(1000, 1000, small)).toEqual({ x: 1, y: 1 });
  });

  it("keeps archived revision markups and does not put a project id in the query", () => {
    const rows = [
      { revision_id: "rev-a", id: "m1" },
      { revision_id: "rev-b", id: "m2" },
    ];
    expect(markupsForRevision(rows, "rev-a").map((item) => item.id)).toEqual(["m1"]);
    expect(markupsForRevision(rows, "rev-b")).toHaveLength(1);
    expect(markupPath("rev-a")).toBe("/v1/site/revisions/rev-a/markups");
    expect(markupPath("rev-a")).not.toContain("pid=");
    expect(markupFilePath("rev-a", "file-1")).not.toContain("pid=");
    expect(markupFilePath("rev-a", "file-1")).toContain("/markups/files/file-1");
  });
});
