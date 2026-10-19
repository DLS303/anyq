"use client";

import { t } from "@/i18n/messages";
import { postSite } from "@/lib/api";
import { openTasksFor, taskTransitionAllowed, type TaskItem } from "@/lib/meetings";
import { toast } from "@/lib/toast";
import type { Locale } from "@/lib/types";

const button =
  "inline-flex min-h-12 shrink-0 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper";

export function MyTasks({
  locale,
  userId,
  items,
  onDone,
}: {
  locale: Locale;
  userId: string;
  items: TaskItem[];
  onDone: () => void;
}) {
  const m = t(locale);
  const mine = openTasksFor(userId, items);

  async function move(item: TaskItem, status: "done" | "cancelled") {
    if (!taskTransitionAllowed(item.status, status)) return;
    try {
      await postSite(`action-items/${item.id}/status`, "", { status, row_version: item.row_version });
      toast(m.hubSaved);
      onDone();
    } catch (err) {
      toast(err instanceof Error ? err.message : m.hubSaveError);
    }
  }

  return (
    <section className="mt-6">
      <h2 className="mb-3 font-serif text-2xl">{m.meetMyTasks}</h2>
      {mine.length === 0 ? <p className="text-sm text-ink/60">{m.meetEmptyTasks}</p> : null}
      <div className="grid gap-2">
        {mine.map((item) => (
          <div key={item.id} className="flex items-center justify-between gap-3 border border-ink/10 bg-white/70 px-3 py-2">
            <p className="text-sm">
              {item.text}
              {item.due_date ? ` · ${item.due_date}` : ""}
            </p>
            <button type="button" className={button} onClick={() => void move(item, "done")}>
              {m.meetDone}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
