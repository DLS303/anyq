export const RFI_NEXT: Record<string, readonly string[]> = {
  open: ["answered", "closed"],
  answered: ["closed"],
  closed: [],
};

export function canTransition(from: string, to: string): boolean {
  return (RFI_NEXT[from] ?? []).includes(to);
}

export function isOverdue(status: string, dueDate: string | null | undefined, today: string): boolean {
  return status === "open" && Boolean(dueDate) && String(dueDate) < today;
}

/** WhatsApp text is the token alone. The sender attaches nothing else. */
export function whatsAppHref(token: string): string {
  return `https://wa.me/?text=${encodeURIComponent(token)}`;
}

export function newId(): string {
  return crypto.randomUUID();
}
