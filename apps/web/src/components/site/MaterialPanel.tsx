"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { newId, whatsAppHref } from "@/lib/rfi";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

type Step = { approver_user_id: string; order: number; decision: string | null; comment: string };
type Item = {
  id: string;
  number: string;
  name: string;
  brand: string;
  status: string;
  need_by: string | null;
  row_version: number;
  overdue: boolean;
  remind: boolean;
  budget_warning: boolean;
  can_decide: boolean;
  comment: string;
  indicative_price: number | null;
  project_only: boolean;
  steps: Step[];
  duplicate_warning?: string | null;
};

type Member = { user_id: string; name: string; role: string };

const field = "w-full min-h-12 border border-ink/15 px-3 py-2 text-sm";
const primary =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";

async function readJson<T>(res: Response): Promise<T> {
  const json = (await res.json()) as { data: T; detail?: string };
  if (!res.ok) {
    const error = new Error(json.detail || res.statusText);
    throw error;
  }
  return json.data;
}

function statusText(status: string, m: ReturnType<typeof t>) {
  switch (status) {
    case "draft":
      return m.matDraft;
    case "in_review":
      return m.matInReview;
    case "approved":
      return m.matApproved;
    case "approved_with_note":
      return m.matApprovedNote;
    case "rejected":
      return m.matRejected;
    case "withdrawn":
      return m.matWithdrawn;
    default:
      return status;
  }
}

export function MaterialPanel({
  locale,
  projectId,
  canWrite,
  members,
  onOverdue,
}: {
  locale: Locale;
  projectId: string;
  canWrite: boolean;
  members: Member[];
  onOverdue?: (count: number) => void;
}) {
  const m = t(locale);
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const approver = members[0]?.user_id || "";

  const load = useCallback(async () => {
    const res = await apiFetch(`/v1/site/projects/${projectId}/material-approvals`);
    if (!res.ok) return;
    const data = await readJson<{ items: Item[]; overdue: number }>(res);
    setItems(data.items);
    onOverdue?.(data.overdue);
  }, [onOverdue, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createItem(form: HTMLFormElement) {
    const fd = new FormData(form);
    const name = String(fd.get("name") || "").trim();
    const brand = String(fd.get("brand") || "").trim();
    const file = fd.get("file");
    const chosen = String(fd.get("approver") || approver);
    if (!name || !brand || !(file instanceof File) || file.size === 0 || !chosen) return;
    setBusy(true);
    setError("");
    try {
      const created = await readJson<Item>(
        await apiFetch(`/v1/site/projects/${projectId}/material-approvals`, {
          method: "POST",
          body: JSON.stringify({
            id: newId(),
            name,
            brand,
            approver_ids: [chosen],
          }),
        }),
      );
      const upload = new FormData();
      upload.set("id", newId());
      upload.set("row_version", String(created.row_version));
      upload.set("kind", "cert");
      upload.set("file", file);
      const saved = await readJson<Item>(
        await apiFetch(`/v1/site/projects/${projectId}/material-approvals/${created.id}/files`, {
          method: "POST",
          body: upload,
        }),
      );
      await readJson(
        await apiFetch(`/v1/site/material-approvals/${created.id}/status`, {
          method: "POST",
          body: JSON.stringify({ status: "in_review", row_version: saved.row_version }),
        }),
      );
      form.reset();
      setOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.featureSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function decide(item: Item, status: string, comment = "") {
    setBusy(true);
    setError("");
    try {
      await readJson(
        await apiFetch(`/v1/site/material-approvals/${item.id}/status`, {
          method: "POST",
          body: JSON.stringify({ status, comment, row_version: item.row_version }),
        }),
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.featureSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function share(item: Item) {
    setBusy(true);
    try {
      const data = await readJson<{ token: string }>(
        await apiFetch(`/v1/site/projects/${projectId}/material-approvals/${item.id}/link`, {
          method: "POST",
          body: JSON.stringify({ id: newId(), expires_in_days: 14 }),
        }),
      );
      setLink(whatsAppHref(data.token));
    } catch (err) {
      setError(err instanceof Error ? err.message : m.featureSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function toRequest(item: Item) {
    setBusy(true);
    try {
      await readJson(
        await apiFetch(`/v1/site/projects/${projectId}/material-approvals/${item.id}/to-request`, { method: "POST" }),
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.featureSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function nextVersion(item: Item) {
    setBusy(true);
    try {
      await readJson(
        await apiFetch(`/v1/site/material-approvals/${item.id}/version`, {
          method: "POST",
          body: JSON.stringify({ id: newId(), row_version: item.row_version }),
        }),
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.featureSaveError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="grid gap-4" data-testid="material-panel">
      {error ? (
        <p className="text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
      {canWrite && !open ? (
        <button type="button" className={primary} data-testid="mat-new" onClick={() => setOpen(true)}>
          {m.matNew}
        </button>
      ) : null}
      {canWrite && open ? (
        <form
          className="grid gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void createItem(event.currentTarget);
          }}
        >
          <input name="name" required placeholder={m.matName} aria-label={m.matName} className={field} data-testid="mat-name" />
          <input name="brand" required placeholder={m.matBrand} aria-label={m.matBrand} className={field} data-testid="mat-brand" />
          <label className="grid gap-1 text-sm">
            {m.matFile}
            <input name="file" required type="file" accept="application/pdf,image/*" className="block w-full text-sm" data-testid="mat-file" />
          </label>
          <select name="approver" defaultValue={approver} aria-label={m.rfiMember} className={field}>
            {members.map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.name}
              </option>
            ))}
          </select>
          <button type="submit" className={primary} disabled={busy} data-testid="mat-send">
            {m.matSend}
          </button>
        </form>
      ) : null}
      {link ? (
        <a className={primary} href={link} target="_blank" rel="noreferrer">
          {m.matShare}
        </a>
      ) : null}
      {items.length === 0 ? <p className="text-sm text-ink/60">{m.matEmpty}</p> : null}
      <ul className="grid gap-3">
        {items.map((item) => (
          <li key={item.id} className="border border-ink/10 p-3" data-testid="mat-item">
            <p className="font-medium">
              {item.number} · {item.name}
              {item.overdue ? <span className="ml-2 text-red-700">{m.rfiOverdue}</span> : null}
              {item.remind ? <span className="ml-2 text-ink/60">{m.matRemind}</span> : null}
            </p>
            <p className="text-sm text-ink/70">
              {item.brand} · {statusText(item.status, m)}
              {item.need_by ? ` · ${m.matNeedBy}: ${item.need_by}` : ""}
            </p>
            {item.project_only ? <p className="text-xs text-ink/50">{m.matProjectOnly}</p> : null}
            {item.budget_warning ? <p className="text-sm text-amber-800">{m.matBudget}</p> : null}
            {item.indicative_price != null ? <p className="text-sm">{item.indicative_price}</p> : null}
            {item.duplicate_warning ? <p className="text-sm text-amber-800">{m.matDuplicate}</p> : null}
            {item.comment ? <p className="text-sm">{item.comment}</p> : null}
            {canWrite && item.status === "in_review" ? (
              <div className="mt-2 grid gap-2">
                {item.can_decide ? (
                  <>
                    <button type="button" className={primary} disabled={busy} onClick={() => void decide(item, "approved")}>
                      {m.matApprove}
                    </button>
                    <form
                      className="grid gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const comment = String(new FormData(event.currentTarget).get("comment") || "");
                        void decide(item, "approved_with_note", comment);
                      }}
                    >
                      <input name="comment" required placeholder={m.matReason} aria-label={m.matReason} className={field} />
                      <button type="submit" className={primary} disabled={busy}>
                        {m.matApproveNote}
                      </button>
                    </form>
                    <form
                      className="grid gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const comment = String(new FormData(event.currentTarget).get("comment") || "");
                        void decide(item, "rejected", comment);
                      }}
                    >
                      <input name="comment" required placeholder={m.matReason} aria-label={m.matReason} className={field} data-testid="mat-reason" />
                      <button type="submit" className={primary} disabled={busy} data-testid="mat-reject">
                        {m.matReject}
                      </button>
                    </form>
                  </>
                ) : null}
                <button type="button" className="min-h-12 text-sm underline" disabled={busy} onClick={() => void share(item)}>
                  {m.matShare}
                </button>
                <button type="button" className="min-h-12 text-sm underline" disabled={busy} onClick={() => void decide(item, "withdrawn")}>
                  {m.matWithdraw}
                </button>
              </div>
            ) : null}
            {item.status === "approved" || item.status === "approved_with_note" ? (
              <button type="button" className={`${primary} mt-2`} disabled={busy} data-testid="mat-to-request" onClick={() => void toRequest(item)}>
                {m.matToRequest}
              </button>
            ) : null}
            {item.status === "rejected" ? (
              <button type="button" className={`${primary} mt-2`} disabled={busy} onClick={() => void nextVersion(item)}>
                {m.matNewVersion}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
