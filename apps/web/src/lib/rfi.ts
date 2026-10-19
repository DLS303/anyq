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

/** WhatsApp text is the public reply page. The sender attaches nothing else. */
export function whatsAppHref(origin: string, locale: string, token: string): string {
  const base = origin.replace(/\/$/, "");
  const page = `${base}/${locale}/r/rfi/${token}`;
  return `https://wa.me/?text=${encodeURIComponent(page)}`;
}

export function newId(): string {
  return crypto.randomUUID();
}
