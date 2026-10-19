import { preparePhoto } from "@/lib/photos";
import { ApiError, apiFetch, fetchAuthorizedBlob } from "@/lib/api";

export type PunchStatus = "open" | "fixed" | "accepted" | "returned";

export type PunchHistory = {
  at: string;
  actor_id: string;
  from_status: string;
  to_status: string;
};

export type PunchPhotoItem = {
  id: string;
  company_id: string;
  project_id: string;
  title: string;
  location: string;
  trade: string;
  status: PunchStatus;
  assignee_id: string | null;
  due_date: string | null;
  photos_before: string[];
  photos_after: string[];
  closed_by: string | null;
  closed_at: string | null;
  author_id: string;
  created_at: string;
  updated_at: string;
  row_version: number;
  deleted_at: string | null;
  overdue: boolean;
  history: PunchHistory[];
  can_fix: boolean;
  can_accept: boolean;
  push?: { text: string; id: string };
};

const STATUSES = new Set(["open", "fixed", "accepted", "returned"]);

export const PUNCH_TRANSITIONS: Array<[string, PunchStatus, PunchStatus]> = [
  ["member", "open", "fixed"],
  ["member", "returned", "fixed"],
  ["author", "fixed", "accepted"],
  ["supervisor", "fixed", "accepted"],
  ["author", "fixed", "returned"],
  ["supervisor", "fixed", "returned"],
];

export function migratePunchStatus(status: string): PunchStatus | "open" {
  if (status === "ready") return "fixed";
  if (status === "closed") return "accepted";
  if (STATUSES.has(status)) return status as PunchStatus;
  return "open";
}

export function isOverdue(due: string | null | undefined, status: string, today: string) {
  return Boolean(due) && String(due) < today && status !== "accepted";
}

/** List path. Filters never copy a project id from the query. */
export function punchListPath(projectId: string, filters: { status?: string; assignee?: string; overdue?: boolean; mine?: boolean; pid?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.assignee) params.set("assignee", filters.assignee);
  if (filters.overdue) params.set("overdue", "1");
  if (filters.mine) params.set("mine", "1");
  const query = params.toString();
  return `/v1/site/projects/${encodeURIComponent(projectId)}/punch-items${query ? `?${query}` : ""}`;
}

export function punchFilePath(projectId: string, punchId: string, fileId: string) {
  return `/v1/site/projects/${encodeURIComponent(projectId)}/punch-items/${encodeURIComponent(punchId)}/files/${encodeURIComponent(fileId)}`;
}

export function transitionFailure(actors: string[], from: string, to: string, hasAfter: boolean): 409 | 403 | null {
  const allowed = actors.some((actor) => PUNCH_TRANSITIONS.some(([name, src, dst]) => name === actor && src === from && dst === to));
  const exists = PUNCH_TRANSITIONS.some(([, src, dst]) => src === from && dst === to);
  if (!allowed && exists) return 403;
  if (!allowed) return 409;
  if ((to === "fixed" || to === "accepted") && !hasAfter) return 409;
  return null;
}

export function gateResult(status: number) {
  if (status === 404) return "missing";
  if (status === 409) return "conflict";
  if (status === 403) return "forbidden";
  return "ok";
}

type FetchLike = (path: string, init?: RequestInit) => Promise<{ status: number }>;

/** Client gate: a foreign company is missing on read, write, file, and link. */
export async function punchRequest(path: string, init: RequestInit | undefined, fetchImpl: FetchLike) {
  const response = await fetchImpl(path, init);
  const gate = gateResult(response.status);
  if (gate === "missing" || gate === "conflict" || gate === "forbidden") {
    const error = new Error(gate);
    (error as Error & { status: number }).status = response.status;
    throw error;
  }
  return response;
}

async function readPunch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  const json = (await res.json()) as { data?: T; detail?: string };
  if (!res.ok) throw new ApiError(typeof json.detail === "string" ? json.detail : res.statusText, res.status);
  return json.data as T;
}

export function fetchPunchItems(projectId: string, filters: { status?: string; assignee?: string; overdue?: boolean; mine?: boolean } = {}) {
  return readPunch<PunchPhotoItem[]>(punchListPath(projectId, filters));
}

export function createPunchItem(projectId: string, body: { id: string; title: string; due_date?: string; location?: string; trade?: string; assignee_id?: string }) {
  return readPunch<PunchPhotoItem>(`/v1/site/projects/${projectId}/punch-items`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function uploadPunchPhoto(projectId: string, punchId: string, file: File, fields: { id: string; file_id: string; phase: "before" | "after"; row_version: number }) {
  const prepared = await preparePhoto(file);
  const body = new FormData();
  body.set("id", fields.id);
  body.set("file_id", fields.file_id);
  body.set("phase", fields.phase);
  body.set("row_version", String(fields.row_version));
  body.set("file", prepared);
  return readPunch<PunchPhotoItem>(`/v1/site/projects/${projectId}/punch-items/${punchId}/photos`, { method: "POST", body });
}

export function setPunchItemStatus(projectId: string, punchId: string, status: PunchStatus, rowVersion: number) {
  return readPunch<PunchPhotoItem>(`/v1/site/projects/${projectId}/punch-items/${punchId}/status`, {
    method: "POST",
    body: JSON.stringify({ status, row_version: rowVersion }),
  });
}

export function punchPdfPath(projectId: string) {
  return `/v1/site/projects/${encodeURIComponent(projectId)}/punch-items.pdf`;
}

export function fetchPunchPdf(projectId: string) {
  return fetchAuthorizedBlob(punchPdfPath(projectId));
}
