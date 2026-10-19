"use client";

import { useState } from "react";
import { t } from "@/i18n/messages";
import { postSite } from "@/lib/api";
import { carryTips, type PlanMeeting, type TaskItem, type TaskPerson } from "@/lib/meetings";
import { todayAlmaty } from "@/lib/report";
import { useGuardedSubmit } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

const field = "w-full min-h-12 border border-ink/15 bg-white px-3 py-2 text-sm";
const button =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";
const quiet =
  "inline-flex min-h-12 items-center justify-center rounded-full border border-ink/20 bg-white px-4 text-sm";

type Row = { text: string; assignee_id: string; due_date: string };

async function openProtocol(meetingId: string) {
  const token = localStorage.getItem("superapp_token");
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`/v1/site/meetings/${meetingId}/file`, { headers });
  if (!res.ok) throw new Error(String(res.status));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
}

export function MeetingForm({
  locale,
  projectId,
  members,
  plans,
  tasks,
  onDone,
}: {
  locale: Locale;
  projectId: string;
  members: TaskPerson[];
  plans: PlanMeeting[];
  tasks: TaskItem[];
  onDone: () => void;
}) {
  const m = t(locale);
  const { submitting, submit, error } = useGuardedSubmit(m.hubSaved, m.hubSaveError, onDone);
  const first = members[0]?.user_id || "";
  const [rows, setRows] = useState<Row[]>([{ text: "", assignee_id: first, due_date: "" }]);
  const carried = carryTips(tasks);

  return (
    <div className="mb-4 grid gap-3">
      <form
        className="grid gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const fd = new FormData(form);
          void submit(async (key) => {
            const filled = rows.filter((row) => row.text.trim() || row.assignee_id || row.due_date);
            if (!filled.length || filled.some((row) => !row.text.trim() || !row.assignee_id || !row.due_date)) {
              throw new Error(m.meetDue);
            }
            const items = filled.map((row) => ({
              id: crypto.randomUUID(),
              text: row.text.trim(),
              assignee_id: row.assignee_id,
              due_date: row.due_date,
              source: "meeting" as const,
            }));
            await postSite(
              `projects/${projectId}/meeting-tasks`,
              "",
              {
                id: crypto.randomUUID(),
                title: String(fd.get("title") || ""),
                day: String(fd.get("day") || ""),
                agenda: String(fd.get("agenda") || ""),
                participants: Array.from(new Set(items.map((row) => row.assignee_id))),
                action_items: items,
              },
              key,
            );
            setRows([{ text: "", assignee_id: first, due_date: "" }]);
            return form;
          });
        }}
      >
        <p className="text-sm text-ink/70">{m.meetRow}</p>
        {error ? (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}
        <input name="title" placeholder={m.meetTitle} aria-label={m.meetTitle} className={field} />
        <input name="day" type="date" defaultValue={todayAlmaty()} aria-label={m.meetDate} className={field} />
        <textarea name="agenda" placeholder={m.meetAgenda} aria-label={m.meetAgenda} className={`${field} min-h-20`} />
        {members.length === 0 ? <p className="text-sm text-ink/70">{m.meetNoPeople}</p> : null}
        {rows.map((row, index) => (
          <div key={index} className="grid gap-2 border border-ink/10 p-2">
            <input
              required
              value={row.text}
              placeholder={m.meetTask}
              aria-label={m.meetTask}
              className={field}
              onChange={(event) =>
                setRows((prev) => prev.map((item, i) => (i === index ? { ...item, text: event.target.value } : item)))
              }
            />
            <select
              required
              aria-label={m.meetWho}
              value={row.assignee_id}
              className={field}
              onChange={(event) =>
                setRows((prev) => prev.map((item, i) => (i === index ? { ...item, assignee_id: event.target.value } : item)))
              }
            >
              <option value="">{m.meetWho}</option>
              {members.map((person) => (
                <option key={person.user_id} value={person.user_id}>
                  {person.name}
                </option>
              ))}
            </select>
            <input
              required
              type="date"
              aria-label={m.meetDue}
              value={row.due_date}
              className={field}
              onChange={(event) =>
                setRows((prev) => prev.map((item, i) => (i === index ? { ...item, due_date: event.target.value } : item)))
              }
            />
          </div>
        ))}
        <button
          type="button"
          className={quiet}
          onClick={() => setRows((prev) => [...prev, { text: "", assignee_id: first, due_date: "" }])}
        >
          {m.meetAddTask}
        </button>
        <button className={button} disabled={submitting || members.length === 0}>
          {m.meetCreate}
        </button>
      </form>
      {carried.length ? (
        <div className="grid gap-1 text-sm text-ink/70">
          {carried.map((item) => (
            <p key={item.id}>
              {item.text} · {item.due_date}
              {item.carried_from_id ? ` · ${m.meetCarried}` : ""}
            </p>
          ))}
        </div>
      ) : null}
      {plans.map((plan) => (
        <div key={plan.id} className="flex items-center justify-between gap-3 border border-ink/10 px-3 py-2">
          <p className="text-sm">
            {(plan.meeting_date || plan.day || "") + (plan.title ? ` · ${plan.title}` : "")}
          </p>
          <button type="button" className={quiet} onClick={() => void openProtocol(plan.id).catch(() => undefined)}>
            {m.meetProtocol}
          </button>
        </div>
      ))}
    </div>
  );
}
