"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

type PublicRfi = {
  number: string;
  title: string;
  question: string;
  answer: string;
  status: string;
  due_date: string | null;
  project_title: string;
  answered: boolean;
};

export function RfiReply({ locale, token }: { locale: Locale; token: string }) {
  const m = t(locale);
  const [item, setItem] = useState<PublicRfi | null>(null);
  const [missing, setMissing] = useState<"none" | "missing" | "expired">("none");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancel = false;
    apiFetch(`/v1/public/rfi/${encodeURIComponent(token)}`, { auth: false })
      .then(async (res) => {
        if (cancel) return;
        if (res.status === 410) {
          setMissing("expired");
          return;
        }
        if (!res.ok) {
          setMissing("missing");
          return;
        }
        const json = (await res.json()) as { data: PublicRfi };
        setItem(json.data);
      })
      .catch(() => {
        if (!cancel) setMissing("missing");
      });
    return () => {
      cancel = true;
    };
  }, [token]);

  async function submit(answer: string) {
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch(`/v1/public/rfi/${encodeURIComponent(token)}`, {
        method: "POST",
        auth: false,
        body: JSON.stringify({ answer }),
      });
      if (res.status === 410) {
        setMissing("expired");
        return;
      }
      if (!res.ok) {
        setMissing("missing");
        return;
      }
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="mx-auto max-w-lg min-w-0 py-6">
      <h1 className="text-2xl font-medium">{m.rfiReplyTitle}</h1>
      {missing === "expired" ? <p className="mt-3 text-sm text-ink/70">{m.rfiReplyExpired}</p> : null}
      {missing === "missing" ? <p className="mt-3 text-sm text-ink/70">{m.rfiReplyMissing}</p> : null}
      {error ? (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
      {item ? (
        <div className="mt-4 grid gap-3">
          <p className="text-sm text-ink/60">{item.project_title}</p>
          <p className="font-medium">{item.number}</p>
          <p>{item.question}</p>
          {item.due_date ? (
            <p className="text-sm text-ink/60">
              {m.rfiDue}: {item.due_date}
            </p>
          ) : null}
          {sent || item.answered ? <p>{m.rfiReplySent}</p> : null}
          {item.answer ? (
            <p>
              {m.rfiAnswerLabel}: {item.answer}
            </p>
          ) : null}
          {!item.answered && !sent ? (
            <form
              className="grid gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                const answer = String(new FormData(event.currentTarget).get("answer") || "").trim();
                if (!answer) return;
                void submit(answer);
              }}
            >
              <textarea
                name="answer"
                required
                data-testid="rfi-public-answer"
                placeholder={m.rfiAnswerLabel}
                className="min-h-24 w-full border border-ink/15 px-3 py-2 text-sm"
              />
              <button
                type="submit"
                disabled={busy}
                className="inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50"
              >
                {m.rfiAnswerSend}
              </button>
            </form>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
