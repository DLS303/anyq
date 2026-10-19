"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

type PublicItem = {
  number: string;
  name: string;
  brand: string;
  status: string;
  need_by: string | null;
  decided: boolean;
  budget_warning: boolean;
};

const field = "w-full min-h-12 border border-ink/15 px-3 py-2 text-sm";
const primary =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";

export function MaterialReply({ locale, token }: { locale: Locale; token: string }) {
  const m = t(locale);
  const [item, setItem] = useState<PublicItem | null>(null);
  const [missing, setMissing] = useState<"none" | "missing" | "expired">("none");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancel = false;
    apiFetch(`/v1/public/material/${encodeURIComponent(token)}`, { auth: false })
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
        const json = (await res.json()) as { data: PublicItem };
        setItem(json.data);
      })
      .catch(() => {
        if (!cancel) setMissing("missing");
      });
    return () => {
      cancel = true;
    };
  }, [token]);

  async function send(decision: string, comment = "") {
    setBusy(true);
    setError("");
    try {
      const res = await apiFetch(`/v1/public/material/${encodeURIComponent(token)}`, {
        method: "POST",
        auth: false,
        body: JSON.stringify({ decision, comment }),
      });
      if (!res.ok) {
        setError(m.featureSaveError);
        return;
      }
      setSent(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto grid min-h-screen max-w-lg gap-4 p-4">
      <h1 className="text-2xl font-medium">{m.matReplyTitle}</h1>
      {missing === "expired" ? <p className="text-sm text-ink/70">{m.matReplyExpired}</p> : null}
      {missing === "missing" ? <p className="text-sm text-ink/70">{m.matReplyMissing}</p> : null}
      {item ? (
        <section className="grid gap-3">
          <p className="font-medium">
            {item.number} · {item.name}
          </p>
          <p className="text-sm text-ink/70">
            {item.brand}
            {item.need_by ? ` · ${m.matNeedBy}: ${item.need_by}` : ""}
          </p>
          {item.budget_warning ? <p className="text-sm text-amber-800">{m.matBudget}</p> : null}
          {sent || item.decided ? <p>{m.matReplySent}</p> : null}
          {!sent && !item.decided ? (
            <div className="grid gap-2">
              <button type="button" className={primary} disabled={busy} data-testid="mat-public-approve" onClick={() => void send("approved")}>
                {m.matApprove}
              </button>
              <form
                className="grid gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const comment = String(new FormData(event.currentTarget).get("comment") || "");
                  void send("rejected", comment);
                }}
              >
                <input name="comment" required placeholder={m.matReason} aria-label={m.matReason} className={field} />
                <button type="submit" className={primary} disabled={busy}>
                  {m.matReject}
                </button>
              </form>
            </div>
          ) : null}
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
        </section>
      ) : null}
    </main>
  );
}
