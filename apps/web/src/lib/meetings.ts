/** Client rules for meeting tasks. The server is the source of truth. */

export const MEETING_REQUIRED_FIELDS = ["text", "assignee_id", "due_date"] as const;

export type TaskItem = {
  id: string;
  meeting_id: string | null;
  text: string;
  assignee_id: string | null;
  due_date: string | null;
  status: string;
  carried_from_id?: string | null;
  row_version: number;
  deleted_at?: string | null;
  source?: string;
};

export type PlanMeeting = {
  id: string;
  title: string;
  day?: string;
  meeting_date?: string;
  agenda?: string;
};

export type TaskPerson = {
  user_id: string;
  name: string;
  role?: string;
};

const ALLOWED: Record<string, string[]> = {
  open: ["done", "cancelled"],
};

export function taskTransitionAllowed(from: string, to: string) {
  return (ALLOWED[from] || []).includes(to);
}

export function carryTips<T extends { id: string; status: string; carried_from_id?: string | null; deleted_at?: string | null }>(
  items: T[],
): T[] {
  const live = items.filter((item) => !item.deleted_at);
  const superseded = new Set(live.map((item) => item.carried_from_id).filter((id): id is string => Boolean(id)));
  return live.filter((item) => item.status === "open" && !superseded.has(item.id));
}

export function openTasksFor(userId: string, items: TaskItem[]) {
  return carryTips(items).filter((item) => item.assignee_id === userId);
}

export function protocolLine(text: string, role: string, due: string, phones: string[], names: string[]) {
  const hidden = new Set([...phones, ...names].filter(Boolean));
  const roleLabel = role || "member";
  const parts = [text, roleLabel, due].filter((part) => part && !hidden.has(part));
  return parts.join(" · ");
}

/** Access uses the path id. A query pid must not replace it. */
export function pathWins(pathId: string, queryPid: string | null) {
  if (queryPid && queryPid !== pathId) return pathId;
  return pathId;
}
