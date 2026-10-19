export const SUBMITTAL_REQUIRED = ["name", "brand", "file"] as const;

export const SUBMITTAL_NEXT: Record<string, readonly string[]> = {
  draft: ["in_review", "withdrawn"],
  in_review: ["approved", "approved_with_note", "rejected", "withdrawn"],
  approved: [],
  approved_with_note: [],
  rejected: [],
  withdrawn: [],
};

export const SEND_TAPS = 3;
export const DECIDE_TAPS = 2;

export function canTransition(from: string, to: string): boolean {
  return (SUBMITTAL_NEXT[from] ?? []).includes(to);
}

export function isOverdue(status: string, needBy: string | null | undefined, today: string): boolean {
  return (status === "draft" || status === "in_review") && Boolean(needBy) && String(needBy) < today;
}

export function overdueCount(items: { overdue?: boolean }[]): number {
  return items.filter((item) => item.overdue).length;
}

export function priceShown(price: number | null | undefined, sourceFileId: string | null | undefined): boolean {
  return price != null && Boolean(sourceFileId);
}

export function brandAllowed(approved: string, analogs: string[], offered: string): boolean {
  const brand = offered.trim().toLowerCase();
  if (!brand) return true;
  return [approved, ...analogs].some((item) => item.trim().toLowerCase() === brand);
}
