"use client";

import { useState } from "react";
import { createInvitation, listInvitations, revokeInvitation, type Invitation } from "@/lib/api";
import { siteRoleLabel } from "@/lib/report";
import { useAsync } from "@/lib/useAsync";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

const ROLES = ["supervisor", "foreman", "procurement", "customer", "specialist", "moderator"] as const;

function statusLabel(status: string, m: ReturnType<typeof t>) {
  if (status === "open") return m.inviteStatusOpen;
  if (status === "used") return m.inviteStatusUsed;
  if (status === "revoked") return m.inviteStatusRevoked;
  if (status === "expired") return m.inviteStatusExpired;
  return status;
}

export function InvitePanel({ locale, projectId }: { locale: Locale; projectId?: string }) {
  const m = t(locale);
  const [role, setRole] = useState<(typeof ROLES)[number]>("foreman");
  const [link, setLink] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const query = useAsync(
    (signal) => listInvitations(projectId).then((rows) => (signal.aborted ? [] : rows)),
    [projectId ?? ""],
  );

  function absolute(path: string) {
    return `${window.location.origin}/${locale}${path.startsWith("/") ? path : `/${path}`}`;
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await createInvitation(role, projectId);
      const url = created.path ? absolute(created.path) : "";
      setLink(url);
      await query.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setNotice(m.inviteCopied);
  }

  async function revoke(row: Invitation) {
    setError("");
    try {
      await revokeInvitation(row.id);
      if (link.includes(row.id)) setLink("");
      await query.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : m.hubSaveError);
    }
  }

  const whatsApp = link ? `https://wa.me/?text=${encodeURIComponent(m.inviteWhatsAppText.replace("{url}", link))}` : "";

  return (
    <section className="mb-4 grid gap-3 border border-ink/10 bg-white/70 p-4">
      <div>
        <h3 className="font-medium">{m.inviteTitle}</h3>
        <p className="mt-1 text-sm text-ink/60">{m.inviteLead}</p>
      </div>
      <form className="grid gap-2" onSubmit={(event) => void create(event)}>
        <label className="grid gap-1 text-sm">
          {m.memberRole}
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as (typeof ROLES)[number])}
            className="min-h-12 border border-ink/15 bg-white px-2 text-sm"
          >
            {ROLES.map((item) => (
              <option key={item} value={item}>
                {siteRoleLabel(item, m)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          disabled={busy}
          className="inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50"
        >
          {m.inviteCreate}
        </button>
      </form>
      {link ? (
        <div className="grid gap-2">
          <input readOnly value={link} className="min-h-12 border border-ink/15 bg-paper px-2 text-sm" />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="min-h-11 rounded-full border border-ink/15 px-4 text-sm" onClick={() => void copy()}>
              {m.inviteCopy}
            </button>
            <a className="inline-flex min-h-11 items-center rounded-full border border-ink/15 px-4 text-sm" href={whatsApp} target="_blank" rel="noreferrer">
              {m.inviteWhatsApp}
            </a>
          </div>
        </div>
      ) : null}
      {notice ? <p className="text-sm text-pine">{notice}</p> : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <ul className="grid gap-2">
        {(query.data ?? []).map((row) => (
          <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>
              {siteRoleLabel(row.role, m)} · {statusLabel(row.status, m)} · {m.inviteExpires.replace("{date}", row.expires_at.slice(0, 10))}
            </span>
            {row.status === "open" ? (
              <button type="button" className="min-h-11 text-xs underline" onClick={() => void revoke(row)}>
                {m.inviteRevoke}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
