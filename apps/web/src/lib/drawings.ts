export type DrawingRev = {
  id: string;
  rev: string;
  file_id: string;
  is_current: boolean;
  row_version: number;
};

export type DrawingSheet = {
  id: string;
  project_id: string;
  company_id: string;
  code: string;
  title: string;
  row_version: number;
  current_rev: string;
  revisions: DrawingRev[];
  set_title?: string;
  discipline?: string;
};

export function drawingSheetsPath(projectId: string) {
  return `/v1/site/projects/${encodeURIComponent(projectId)}/drawing-sheets`;
}

export function drawingCreatePath(projectId: string) {
  return `/v1/site/projects/${encodeURIComponent(projectId)}/drawings`;
}

export function drawingRevisionPath(drawingId: string) {
  return `/v1/site/drawings/${encodeURIComponent(drawingId)}/revisions`;
}

export function drawingFilePath(drawingId: string, rev: string) {
  const base = `/v1/site/drawings/${encodeURIComponent(drawingId)}/file`;
  return `${base}?rev=${encodeURIComponent(rev)}`;
}

export function gateStatus(status: number): "hidden" | "conflict" | "ready" {
  if (status === 404) return "hidden";
  if (status === 409) return "conflict";
  return "ready";
}

export function currentRevision<T extends { is_current: boolean }>(revs: T[]) {
  return revs.find((item) => item.is_current);
}

export function hasNewerVersion(revs: { rev: string; is_current: boolean }[], selected: string) {
  const current = currentRevision(revs);
  return Boolean(current && current.rev !== selected);
}

export function applyUploadedRevision<T extends { rev: string; is_current: boolean }>(
  revs: T[],
  next: T,
): T[] | 409 {
  if (revs.some((item) => item.rev === next.rev)) return 409;
  const archived = revs.map((item) => ({ ...item, is_current: false }));
  return [...archived, { ...next, is_current: true }];
}

export function sheetTitle(fileName: string) {
  const bare = fileName.replace(/\.[^.]+$/, "").trim();
  return bare || "sheet";
}
