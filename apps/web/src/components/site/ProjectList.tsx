"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { memo, useState } from "react";
import { createSiteProject, fetchProjectsPage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import type { Msg } from "@/i18n/messages";
import { useMessages } from "@/lib/i18n";
import { LongList } from "@/components/ui/LongList";
import { ErrorRetry, LoadingSkeleton, useAsync } from "@/lib/useAsync";
import { toast } from "@/lib/toast";
import type { Locale } from "@/lib/types";

type Snap = {
  project: { id: string; slug: string; title: string; address: string };
  health: string;
  budget_kzt: number | null;
  open_rfi: number;
  open_punch: number;
};

const PAGE = 24;

function healthLabel(health: string, m: Msg) {
  if (health === "green") return m.healthOk;
  if (health === "red") return m.healthBad;
  return m.healthWarn;
}

const ProjectRow = memo(function ProjectRow({
  row,
  locale,
  m,
}: {
  row: Snap;
  locale: Locale;
  m: Msg;
}) {
  return (
    <Link
      href={`/${locale}/site/${row.project.id}`}
      prefetch={false}
      className="block border border-ink/10 bg-white/60 p-5 hover:border-pine"
    >
      <div className="flex justify-between gap-4">
        <div className="min-w-0">
          <h2 className="font-serif text-2xl">{row.project.title}</h2>
          <p className="mt-1 text-sm text-ink/55">{row.project.address}</p>
        </div>
        <p className="text-xs uppercase tracking-wider">{healthLabel(row.health, m)}</p>
      </div>
      <p className="mt-3 text-sm">
        {row.budget_kzt == null ? m.objectBudgetEmpty : money(row.budget_kzt, locale)} · {m.hubIssueRfi} {row.open_rfi} · {m.hubIssuePunch} {row.open_punch}
      </p>
    </Link>
  );
});

export function ProjectList({ locale }: { locale: Locale }) {
  const m = useMessages();
  const router = useRouter();
  const { user } = useAuth();
  const canCreate = user?.role === "admin" || user?.role === "owner";
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState<Snap[]>([]);
  const query = useAsync(async (signal) => {
    if (!localStorage.getItem("superapp_token")) return { items: [] as Snap[], total: 0 };
    const page = await fetchProjectsPage(PAGE, 0, signal);
    return { items: page.items as Snap[], total: page.total ?? page.items.length };
  }, []);
  const first = query.data?.items ?? [];
  const items = more.length ? [...first, ...more] : first;
  const total = query.data?.total ?? items.length;

  async function loadMore() {
    const page = await fetchProjectsPage(PAGE, items.length);
    setMore((current) => [...current, ...(page.items as Snap[])]);
  }

  async function create(form: HTMLFormElement) {
    const fd = new FormData(form);
    const title = String(fd.get("title") || "").trim();
    const address = String(fd.get("address") || "").trim();
    const deadline = String(fd.get("deadline") || "").trim();
    const budgetRaw = String(fd.get("budget") || "").trim();
    const body: { title: string; address: string; deadline?: string; budget_kzt?: number } = { title, address };
    if (deadline) body.deadline = deadline;
    if (budgetRaw) body.budget_kzt = Number(budgetRaw);
    setBusy(true);
    try {
      const created = await createSiteProject(body);
      toast(m.hubSaved);
      router.push(`/${locale}/site/${created.id}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  const creator = canCreate ? (
    <div className="mb-4">
      {open ? (
        <form
          className="grid gap-2 border border-ink/10 bg-white/70 p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void create(event.currentTarget);
          }}
        >
          <input name="title" required minLength={3} maxLength={120} placeholder={m.objectName} aria-label={m.objectName} className="min-h-12 border border-ink/15 px-3 text-sm" />
          <input name="address" maxLength={200} placeholder={m.objectAddress} aria-label={m.objectAddress} className="min-h-12 border border-ink/15 px-3 text-sm" />
          <input name="deadline" type="date" aria-label={m.objectDeadline} className="min-h-12 border border-ink/15 px-3 text-sm" />
          <input name="budget" type="number" min={0} step={1} placeholder={m.objectBudget} aria-label={m.objectBudget} className="min-h-12 border border-ink/15 px-3 text-sm" />
          <button type="submit" className="inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50" disabled={busy}>
            {m.objectCreate}
          </button>
        </form>
      ) : (
        <button type="button" className="inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper" onClick={() => setOpen(true)}>
          {m.objectNew}
        </button>
      )}
    </div>
  ) : null;

  if (query.loading) return <LoadingSkeleton label={m.hubLoading} />;
  if (query.status === "error") {
    return <ErrorRetry message={m.listLoadError} retryLabel={m.hubRetry} onRetry={query.reload} />;
  }
  if (!items.length) {
    return (
      <div>
        {creator}
        <div className="border border-ink/10 bg-white/50 p-6 text-center">
          <p className="text-sm text-ink/70">{m.listEmpty}</p>
          {user ? (
            <Link href={`/${locale}/crm`} className="mt-4 inline-flex min-h-12 items-center text-sm underline">
              {m.hubFromCrm}
            </Link>
          ) : (
            <Link href={`/${locale}/login`} className="mt-4 inline-flex min-h-12 items-center text-sm underline">
              {m.navLogin}
            </Link>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {creator}
      <LongList
        items={items}
        pageSize={PAGE}
        getKey={(row) => row.project.id}
        render={(row) => <ProjectRow row={row} locale={locale} m={m} />}
      />
      {items.length < total ? (
        <button type="button" className="min-h-12 text-sm underline" onClick={() => void loadMore()}>
          {m.listMore}
        </button>
      ) : null}
    </div>
  );
}
