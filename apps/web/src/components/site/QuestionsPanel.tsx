"use client";

import { useState } from "react";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";
import { MaterialPanel } from "./MaterialPanel";
import { RfiPanel } from "./RfiPanel";

type Member = { user_id: string; name: string; role: string };

function fill(template: string, values: Record<string, string | number>) {
  return Object.entries(values).reduce((text, [key, value]) => text.split(`{${key}}`).join(String(value)), template);
}

export function QuestionsPanel({
  locale,
  projectId,
  canWrite,
  members,
  showQuestions,
  showMaterials,
  onChange,
}: {
  locale: Locale;
  projectId: string;
  canWrite: boolean;
  members: Member[];
  showQuestions: boolean;
  showMaterials: boolean;
  onChange: () => void;
}) {
  const m = t(locale);
  const [filter, setFilter] = useState<"questions" | "materials">(showQuestions ? "questions" : "materials");
  const [questionOverdue, setQuestionOverdue] = useState(0);
  const [materialOverdue, setMaterialOverdue] = useState(0);
  const active = filter === "materials" || !showQuestions ? "materials" : "questions";
  const overdue = active === "questions" ? questionOverdue : materialOverdue;
  const chip = "min-h-12 rounded-full px-4 text-sm";

  return (
    <section className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-medium">{m.tabRfi}</h2>
        <p className="text-sm text-red-700" data-testid="overdue-count">
          {fill(m.matOverdueCount, { n: overdue })}
        </p>
      </div>
      {showQuestions && showMaterials ? (
        <div className="flex gap-2">
          <button
            type="button"
            className={`${chip} ${active === "questions" ? "bg-pine text-paper" : "border border-ink/15"}`}
            data-testid="filter-questions"
            onClick={() => setFilter("questions")}
          >
            {m.matQuestions}
          </button>
          <button
            type="button"
            className={`${chip} ${active === "materials" ? "bg-pine text-paper" : "border border-ink/15"}`}
            data-testid="filter-materials"
            onClick={() => setFilter("materials")}
          >
            {m.matMaterials}
          </button>
        </div>
      ) : null}
      {showQuestions ? (
        <div hidden={active !== "questions"}>
          <RfiPanel
            locale={locale}
            projectId={projectId}
            canWrite={canWrite}
            members={members}
            onChange={onChange}
            embedded
            onOverdue={setQuestionOverdue}
          />
        </div>
      ) : null}
      {showMaterials ? (
        <div hidden={active !== "materials"}>
          <MaterialPanel
            locale={locale}
            projectId={projectId}
            canWrite={canWrite}
            members={members}
            onOverdue={setMaterialOverdue}
          />
        </div>
      ) : null}
    </section>
  );
}
