"use client";

import { useState } from "react";
import { t } from "@/i18n/messages";
import { postSite, uploadPhoto } from "@/lib/api";
import { todayAlmaty } from "@/lib/report";
import { useGuardedSubmit } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

type Result = "pass" | "fail" | "na";
type Item = { label: string; result: Result; comment: string };

const field = "w-full min-h-12 border border-ink/15 bg-white px-3 py-2 text-sm";
const button =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";
const quiet =
  "inline-flex min-h-12 items-center justify-center rounded-full border border-ink/20 bg-white px-4 text-sm";

export function InspectionForm({
  locale,
  projectId,
  onDone,
}: {
  locale: Locale;
  projectId: string;
  onDone: () => void;
}) {
  const m = t(locale);
  const { submitting, submit } = useGuardedSubmit(m.hubSaved, m.hubSaveError, onDone);
  const [items, setItems] = useState<Item[]>([{ label: "", result: "pass", comment: "" }]);

  return (
    <form
      className="mb-4 grid gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const fd = new FormData(form);
        const file = fd.get("photo");
        void submit(async (key) => {
          const cleaned = items
            .map((item) => ({ label: item.label.trim(), result: item.result, comment: item.comment.trim() }))
            .filter((item) => item.label);
          if (!cleaned.length) throw new Error(m.inspItem);
          let photo = "";
          if (file instanceof File && file.size > 0) photo = await uploadPhoto("", file, projectId);
          await postSite(
            `projects/${projectId}/inspections`,
            "",
            {
              title: String(fd.get("title") || ""),
              day: String(fd.get("day") || ""),
              notes: String(fd.get("notes") || ""),
              items: cleaned,
              photo,
            },
            key,
          );
          setItems([{ label: "", result: "pass", comment: "" }]);
          return form;
        });
      }}
    >
      <input name="title" required placeholder={m.inspTitle} className={field} />
      <input name="day" type="date" required defaultValue={todayAlmaty()} className={field} aria-label={m.meetDate} />
      {items.map((item, index) => (
        <div key={index} className="grid gap-2 border border-ink/10 p-2">
          <input
            required={index === 0}
            value={item.label}
            placeholder={m.inspItem}
            className={field}
            onChange={(event) =>
              setItems((prev) => prev.map((row, i) => (i === index ? { ...row, label: event.target.value } : row)))
            }
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <select
              aria-label={m.inspItem}
              value={item.result}
              className={field}
              onChange={(event) =>
                setItems((prev) =>
                  prev.map((row, i) => (i === index ? { ...row, result: event.target.value as Result } : row)),
                )
              }
            >
              <option value="pass">{m.inspPass}</option>
              <option value="fail">{m.inspFail}</option>
              <option value="na">{m.inspNa}</option>
            </select>
            <input
              value={item.comment}
              placeholder={m.inspComment}
              className={field}
              onChange={(event) =>
                setItems((prev) => prev.map((row, i) => (i === index ? { ...row, comment: event.target.value } : row)))
              }
            />
          </div>
        </div>
      ))}
      <button
        type="button"
        className={quiet}
        onClick={() => setItems((prev) => [...prev, { label: "", result: "pass", comment: "" }])}
      >
        {m.inspAddItem}
      </button>
      <textarea name="notes" placeholder={m.inspNotes} className={`${field} min-h-24`} />
      <label className="grid gap-1 text-sm text-ink/70">
        {m.inspPhoto}
        <input name="photo" type="file" accept="image/jpeg,image/png,image/webp" className={field} />
      </label>
      <button className={button} disabled={submitting}>
        {m.inspCreate}
      </button>
    </form>
  );
}
