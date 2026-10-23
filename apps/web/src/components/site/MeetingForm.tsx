"use client";

import { useState } from "react";
import { useMessages } from "@/lib/i18n";
import { postSite } from "@/lib/api";
import { SITE_ROLES, siteRoleLabel, todayAlmaty } from "@/lib/report";
import { useGuardedSubmit } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";

type Person = { role: string; name: string };
type Decision = { text: string; owner_role: string; due: string };

const field = "w-full min-h-12 border border-ink/15 bg-white px-3 py-2 text-sm";
const button =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";
const quiet =
  "inline-flex min-h-12 items-center justify-center rounded-full border border-ink/20 bg-white px-4 text-sm";

function RoleSelect({
  value,
  label,
  onChange,
  locale,
}: {
  value: string;
  label: string;
  onChange: (role: string) => void;
  locale: Locale;
}) {
  const m = useMessages();
  return (
    <select aria-label={label} value={value} className={field} onChange={(event) => onChange(event.target.value)}>
      {SITE_ROLES.map((role) => (
        <option key={role} value={role}>
          {siteRoleLabel(role, m)}
        </option>
      ))}
    </select>
  );
}

export function MeetingForm({
  locale,
  projectId,
  onDone,
}: {
  locale: Locale;
  projectId: string;
  onDone: () => void;
}) {
  const m = useMessages();
  const { submitting, submit } = useGuardedSubmit(m.hubSaved, m.hubSaveError, onDone);
  const [people, setPeople] = useState<Person[]>([{ role: "contractor", name: "" }]);
  const [decisions, setDecisions] = useState<Decision[]>([{ text: "", owner_role: "foreman", due: "" }]);

  return (
    <form
      className="mb-4 grid gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const fd = new FormData(form);
        void submit(async (key) => {
          const participants = people
            .map((person) => ({ role: person.role, name: person.name.trim() }))
            .filter((person) => person.role);
          const decisionItems = decisions
            .map((item) => ({ text: item.text.trim(), owner_role: item.owner_role, due: item.due }))
            .filter((item) => item.text || item.due);
          if (decisionItems.some((item) => !item.text || !item.due)) throw new Error(m.meetDue);
          await postSite(
            `projects/${projectId}/meetings`,
            "",
            {
              title: String(fd.get("title") || ""),
              day: String(fd.get("day") || ""),
              agenda: String(fd.get("agenda") || ""),
              participants,
              decision_items: decisionItems,
            },
            key,
          );
          setPeople([{ role: "contractor", name: "" }]);
          setDecisions([{ text: "", owner_role: "foreman", due: "" }]);
          return form;
        });
      }}
    >
      <input name="title" required placeholder={m.meetTitle} className={field} />
      <input name="day" type="date" required defaultValue={todayAlmaty()} aria-label={m.meetDate} className={field} />
      <textarea name="agenda" required placeholder={m.meetAgenda} className={`${field} min-h-24`} />
      {people.map((person, index) => (
        <div key={index} className="grid gap-2 sm:grid-cols-2">
          <RoleSelect
            locale={locale}
            label={m.meetParticipant}
            value={person.role}
            onChange={(role) => setPeople((prev) => prev.map((row, i) => (i === index ? { ...row, role } : row)))}
          />
          <input
            value={person.name}
            placeholder={m.meetName}
            aria-label={m.meetName}
            className={field}
            onChange={(event) =>
              setPeople((prev) => prev.map((row, i) => (i === index ? { ...row, name: event.target.value } : row)))
            }
          />
        </div>
      ))}
      <button
        type="button"
        className={quiet}
        onClick={() => setPeople((prev) => [...prev, { role: "supervisor", name: "" }])}
      >
        {m.meetAddParticipant}
      </button>
      {decisions.map((item, index) => (
        <div key={index} className="grid gap-2 border border-ink/10 p-2">
          <input
            value={item.text}
            placeholder={m.meetDecision}
            className={field}
            onChange={(event) =>
              setDecisions((prev) => prev.map((row, i) => (i === index ? { ...row, text: event.target.value } : row)))
            }
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <RoleSelect
              locale={locale}
              label={m.meetOwner}
              value={item.owner_role}
              onChange={(owner_role) =>
                setDecisions((prev) => prev.map((row, i) => (i === index ? { ...row, owner_role } : row)))
              }
            />
            <input
              type="date"
              aria-label={m.meetDue}
              value={item.due}
              className={field}
              onChange={(event) =>
                setDecisions((prev) => prev.map((row, i) => (i === index ? { ...row, due: event.target.value } : row)))
              }
            />
          </div>
        </div>
      ))}
      <button
        type="button"
        className={quiet}
        onClick={() => setDecisions((prev) => [...prev, { text: "", owner_role: "foreman", due: "" }])}
      >
        {m.meetAddDecision}
      </button>
      <button className={button} disabled={submitting}>
        {m.meetCreate}
      </button>
    </form>
  );
}
