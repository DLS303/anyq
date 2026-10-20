"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { acceptInvitation, previewInvitation } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { siteRoleLabel } from "@/lib/report";
import { useAsync } from "@/lib/useAsync";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

export function InviteAccept({ locale, token }: { locale: Locale; token: string }) {
  const m = t(locale);
  const router = useRouter();
  const { login } = useAuth();
  const preview = useAsync((signal) => previewInvitation(token, signal), [token]);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const row = preview.data;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!consent) {
      setError(m.consentRequired);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await acceptInvitation(token, {
        email,
        password,
        full_name: fullName,
        phone,
        consent_offer_pd: true,
      });
      login(result.user, result.token);
      router.push(`/${locale}/cabinet`);
    } catch (err) {
      setError(err instanceof Error ? err.message : m.inviteClosed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto grid max-w-lg gap-4">
      <h1 className="font-serif text-3xl">{m.inviteAcceptTitle}</h1>
      {preview.loading ? <p className="text-sm text-ink/60">{m.hubLoading}</p> : null}
      {preview.status === "error" ? <p className="text-sm text-red-700">{m.inviteMissing}</p> : null}
      {row && row.status !== "open" ? <p className="text-sm text-red-700">{m.inviteClosed}</p> : null}
      {row && row.status === "open" ? (
        <form className="grid gap-3 border border-ink/10 bg-white/70 p-4" onSubmit={(event) => void submit(event)}>
          <p className="text-sm text-ink/70">
            {m.inviteAcceptLead} {siteRoleLabel(row.role, m)}
            {row.company ? ` · ${row.company}` : ""}
            {row.project_title ? ` · ${row.project_title}` : ""}
          </p>
          <input
            required
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder={m.fullName}
            className="min-h-12 border border-ink/15 px-2 text-sm"
          />
          <input
            required
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Email"
            className="min-h-12 border border-ink/15 px-2 text-sm"
          />
          <input
            required
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="+7"
            className="min-h-12 border border-ink/15 px-2 text-sm"
          />
          <input
            required
            type="password"
            minLength={6}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={m.password}
            className="min-h-12 border border-ink/15 px-2 text-sm"
          />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-1" />
            <span>{m.consentPd}</span>
          </label>
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50"
          >
            {m.inviteAccept}
          </button>
        </form>
      ) : null}
    </div>
  );
}
