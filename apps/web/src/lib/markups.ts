export const MARKUP_TOOLS = ["arrow", "cloud", "text", "photo"] as const;

export type MarkupTool = (typeof MARKUP_TOOLS)[number];
export type MarkupVisibility = "me" | "project";

export type UnitPoint = { x: number; y: number };
export type Rect = { left: number; top: number; width: number; height: number };

export type ArrowShape = { type: "arrow"; x1: number; y1: number; x2: number; y2: number };
export type CloudShape = { type: "cloud"; x: number; y: number; w: number; h: number };
export type TextShape = { type: "text"; x: number; y: number; text: string };
export type PhotoShape = { type: "photo"; x: number; y: number; w: number; h: number; file_id: string };
export type MarkupShape = ArrowShape | CloudShape | TextShape | PhotoShape;

export type Draft = {
  tool: MarkupTool | null;
  points: UnitPoint[];
  taps: number;
};

const MAX_TAPS = 3;

export function clampUnit(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

export function unitPoint(clientX: number, clientY: number, rect: Rect): UnitPoint {
  const width = rect.width || 1;
  const height = rect.height || 1;
  return {
    x: clampUnit((clientX - rect.left) / width),
    y: clampUnit((clientY - rect.top) / height),
  };
}

export function unitToPixel(point: UnitPoint, rect: Rect) {
  return { x: point.x * rect.width, y: point.y * rect.height };
}

export function idleDraft(): Draft {
  return { tool: null, points: [], taps: 0 };
}

export function beginTool(tool: MarkupTool, taps = 0): Draft {
  return { tool, points: [], taps: taps + 1 };
}

export function placementTaps(tool: MarkupTool) {
  void tool;
  return MAX_TAPS;
}

export function placePoint(draft: Draft, point: UnitPoint): { draft: Draft; ready: MarkupTool | null; points: UnitPoint[] } {
  if (!draft.tool) return { draft, ready: null, points: draft.points };
  const next = { x: clampUnit(point.x), y: clampUnit(point.y) };
  const taps = draft.taps + 1;
  if (draft.tool === "arrow" || draft.tool === "cloud") {
    const points = [...draft.points, next];
    if (points.length < 2) return { draft: { tool: draft.tool, points, taps }, ready: null, points };
    return { draft: idleDraft(), ready: draft.tool, points };
  }
  const points = [next];
  return { draft: { tool: draft.tool, points, taps }, ready: draft.tool, points };
}

export function arrowShape(points: UnitPoint[]): ArrowShape {
  const [start, end] = points;
  return { type: "arrow", x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

export function cloudShape(points: UnitPoint[]): CloudShape {
  const [start, end] = points;
  const x = clampUnit(Math.min(start.x, end.x));
  const y = clampUnit(Math.min(start.y, end.y));
  const w = Math.min(Math.max(Math.abs(start.x - end.x), 0.04), 1 - x);
  const h = Math.min(Math.max(Math.abs(start.y - end.y), 0.04), 1 - y);
  return { type: "cloud", x, y, w, h };
}

export function textShape(point: UnitPoint, text: string): TextShape {
  return { type: "text", x: clampUnit(point.x), y: clampUnit(point.y), text: text.trim() };
}

export function photoShape(point: UnitPoint, fileId: string): PhotoShape {
  const w = 0.22;
  const h = 0.22;
  return {
    type: "photo",
    x: clampUnit(Math.min(point.x, 1 - w)),
    y: clampUnit(Math.min(point.y, 1 - h)),
    w,
    h,
    file_id: fileId,
  };
}

export function finishText(draft: Draft, text: string): { shape: TextShape | null; taps: number } {
  const taps = draft.taps + 1;
  const point = draft.points[0];
  const note = text.trim();
  if (!point || !note) return { shape: null, taps };
  return { shape: textShape(point, note), taps };
}

export function finishPhoto(draft: Draft, fileId: string): { shape: PhotoShape | null; taps: number } {
  const taps = draft.taps + 1;
  const point = draft.points[0];
  if (!point || !fileId) return { shape: null, taps };
  return { shape: photoShape(point, fileId), taps };
}

export function markupPath(revisionId: string) {
  return `/v1/site/revisions/${encodeURIComponent(revisionId)}/markups`;
}

export function markupFilePath(revisionId: string, fileId: string) {
  return `/v1/site/revisions/${encodeURIComponent(revisionId)}/markups/files/${encodeURIComponent(fileId)}`;
}

export function markupsForRevision<T extends { revision_id: string }>(rows: T[], revisionId: string) {
  return rows.filter((row) => row.revision_id === revisionId);
}

export function cloudPath(shape: CloudShape) {
  const cx = shape.x + shape.w / 2;
  const cy = shape.y + shape.h / 2;
  const rx = shape.w / 2;
  const ry = shape.h / 2;
  const steps = 8;
  let path = "";
  for (let index = 0; index <= steps; index += 1) {
    const angle = (Math.PI * 2 * index) / steps;
    const bump = index % 2 === 0 ? 1 : 0.78;
    const x = cx + Math.cos(angle) * rx * bump;
    const y = cy + Math.sin(angle) * ry * bump;
    path += index === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
  }
  return `${path} Z`;
}
