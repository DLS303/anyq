"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { newId, whatsAppHref } from "@/lib/rfi";
import { statusLabel } from "@/lib/report";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

type Contact = {
  id: string;
  full_name: string;
  phone: string;
  email: string;
  organization: string;
};

type RfiItem = {
  id: string;
  number: string;
  title: string;
  question: string;
  answer: string;
  status: string;
  due_date: string | null;
  row_version: number;
  overdue: boolean;
  drawing_revision_id: string | null;
  contact: Contact | null;
};

type Member = { user_id: string; name: string; role: string };

const field = "w-full min-h-12 border border-ink/15 px-3 py-2 text-sm";
const primary =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";

async function readJson<T>(res: Response): Promise<T> {
  const json = (await res.json()) as { data: T; detail?: string };
  if (!res.ok) {
    const error = new Error(json.detail || res.statusText);
    (error as Error & { status?: number }).status = res.status;
    throw error;
  }
  return json.data;
}

export function RfiPanel({
  locale,
  projectId,
  canWrite,
  members,
  onChange,
}: {
  locale: Locale;
  projectId: string;
  canWrite: boolean;
  members: Member[];
  onChange: () => void;
}) {
  const m = t(locale);
  const [items, setItems] = useState<RfiItem[]>([]);
  const [error, setError] = useState("");
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await apiFetch(`/v1/site/projects/${projectId}/rfis`);
    if (!res.ok) return;
    const data = await readJson<RfiItem[]>(res);
    setItems(data);
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createQuestion(form: HTMLFormElement) {
    const fd = new FormData(form);
    const question = String(fd.get("question") || "").trim();
    if (!question) {
      setError(m.fieldRequired);
      return;
    }
    const external = String(fd.get("external") || "") === "1";
    const body: Record<string, unknown> = {
      id: newId(),
      question,
      drawing_revision_id: String(fd.get("drawing") || "").trim() || null,
    };
    const assignee = String(fd.get("assignee") || "").trim();
    if (!external && assignee) body.assignee_user_id = assignee;
    if (external) {
      body.contact = {
        id: newId(),
        full_name: String(fd.get("full_name") || "").trim(),
        phone: String(fd.get("phone") || "").trim(),
        email: String(fd.get("email") || "").trim(),
        organization: String(fd.get("organization") || "").trim(),
      };
    }
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch(`/v1/site/projects/${projectId}/rfis`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      await readJson(res);
      form.reset();
      await load();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function sendAnswer(item: RfiItem, answer: string) {
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch(`/v1/site/rfis/${item.id}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer, row_version: item.row_version }),
      });
      await readJson(res);
      await load();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function closeItem(item: RfiItem) {
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch(`/v1/site/rfis/${item.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "closed", row_version: item.row_version }),
      });
      await readJson(res);
      await load();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function share(item: RfiItem) {
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch(`/v1/site/projects/${projectId}/rfis/${item.id}/link`, {
        method: "POST",
        body: JSON.stringify({ id: newId(), expires_in_days: 14 }),
      });
      const data = await readJson<{ token: string }>(res);
      setLink(whatsAppHref(data.token));
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="grid gap-4">
      <h2 className="text-xl font-medium">{m.tabRfi}</h2>
      {error ? (
        <p className="text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
      {canWrite ? (
        <form
          className="grid gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void createQuestion(event.currentTarget);
          }}
        >
          <textarea
            name="question"
            required
            data-testid="rfi-question"
            placeholder={m.rfiQuestion}
            className={`${field} min-h-24`}
          />
          <details className="text-sm">
            <summary className="min-h-12 cursor-pointer py-3">{m.rfiExternal}</summary>
            <div className="grid gap-2">
              <label className="flex min-h-12 items-center gap-2">
                <input type="checkbox" name="external" value="1" />
                {m.rfiExternal}
              </label>
              <select name="assignee" className={field} defaultValue="">
                <option value="">{m.rfiMember}</option>
                {members.map((member) => (
                  <option key={member.user_id} value={member.user_id}>
                    {member.name}
                  </option>
                ))}
              </select>
              <input name="full_name" placeholder={m.rfiName} className={field} />
              <input name="phone" placeholder={m.rfiPhone} className={field} autoComplete="off" />
              <input name="email" placeholder={m.rfiEmail} className={field} autoComplete="off" />
              <input name="organization" placeholder={m.rfiOrg} className={field} />
              <input name="drawing" placeholder={m.rfiDrawing} className={field} />
            </div>
          </details>
          <button type="submit" className={primary} disabled={busy} data-testid="rfi-send">
            {m.rfiSend}
          </button>
        </form>
      ) : null}
      {link ? (
        <a className={primary} href={link} target="_blank" rel="noreferrer" data-testid="rfi-whatsapp">
          {m.rfiShare}
        </a>
      ) : null}
      {items.length === 0 ? <p className="text-sm text-ink/60">{m.rfiEmpty}</p> : null}
      <ul className="grid gap-3">
        {items.map((item) => (
          <li key={item.id} className="border border-ink/10 p-3" data-testid="rfi-item">
            <p className="font-medium">
              {item.number} · {statusLabel(item.status, m)}
              {item.overdue ? <span className="ml-2 text-red-700">{m.rfiOverdue}</span> : null}
            </p>
            <p className="text-ink/70">{item.question}</p>
            {item.due_date ? (
              <p className="text-xs text-ink/50">
                {m.rfiDue}: {item.due_date}
              </p>
            ) : null}
            {item.contact ? (
              <p className="text-xs text-ink/50">
                {item.contact.full_name} {item.contact.phone}
              </p>
            ) : null}
            {item.answer ? (
              <p className="mt-2">
                {m.rfiAnswerLabel}: {item.answer}
              </p>
            ) : null}
            {canWrite && item.status === "open" ? (
              <form
                className="mt-2 grid gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const answer = String(new FormData(event.currentTarget).get("answer") || "").trim();
                  if (!answer) return;
                  void sendAnswer(item, answer);
                }}
              >
                <textarea name="answer" required placeholder={m.rfiAnswerLabel} className={`${field} min-h-24`} />
                <button type="submit" className={primary} disabled={busy}>
                  {m.rfiAnswerSend}
                </button>
              </form>
            ) : null}
            {canWrite && item.status !== "closed" ? (
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" className={primary} disabled={busy} onClick={() => void closeItem(item)}>
                  {m.rfiClose}
                </button>
                {item.status === "open" ? (
                  <button type="button" className={primary} disabled={busy} onClick={() => void share(item)}>
                    {m.rfiShare}
                  </button>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
