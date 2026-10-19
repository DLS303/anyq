"use client";

import { useState } from "react";
import Link from "next/link";
import { PageNav, usePaged } from "@/components/ui/PagedList";
import { useAuth } from "@/lib/auth";
import { fetchQueue, moderatePlot } from "@/lib/api";
import { titleOf } from "@/lib/format";
import { ErrorRetry, LoadingSkeleton, useAsync, useSubmitLock } from "@/lib/useAsync";
import type { Locale } from "@/lib/types";
import { t } from "@/i18n/messages";
import { toast } from "@/lib/toast";

export function ModerationView({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const actionLock = useSubmitLock();
  const allowed = user?.role === "moderator" || user?.role === "admin";
  const query = useAsync(
    (signal) => (user && allowed ? fetchQueue(user.email, signal) : Promise.resolve([])),
    [user?.email, allowed],
  );
  const plots = query.data ?? [];
  const paged = usePaged(plots, user?.email ?? "");

  if (!user || (user.role !== "moderator" && user.role !== "admin")) {
    return (
      <p>
        {m.needMod}{" "}
        <Link href={`/${locale}/login`} className="underline">
          {m.navLogin}
        </Link>
      </p>
    );
  }

  async function act(id: string, action: "approve" | "revision" | "reject") {
    if (!user || actionLock.pending) return;
    await actionLock.run(async () => {
      try {
        await moderatePlot(user.email, id, action, notes[id] ?? "");
        query.reload();
      } catch (err) {
        toast(err instanceof Error ? err.message : m.hubSaveError);
      }
    });
  }

  return (
    <div className="grid min-w-0 gap-4">
      {query.loading ? <LoadingSkeleton label={m.hubLoading} /> : null}
      {query.status === "error" ? (
        <ErrorRetry message={m.listLoadError} retryLabel={m.retry} onRetry={query.reload} />
      ) : null}
      {!query.loading && query.status !== "error" && plots.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
      {query.status !== "error"
        ? paged.slice.map((plot) => (
        <div key={plot.id} className="border border-ink/10 bg-white/60 p-4">
          <p className="font-serif text-xl">{titleOf(plot, locale)}</p>
          <p className="text-sm text-ink/55 mt-1">
            {plot.cadastral_no} · {plot.district} · {plot.status} · Trust {plot.trust_score}
          </p>
          <p className="text-xs text-ink/45 mt-1">
            газ {plot.gas} · свет {plot.electricity} · красные линии {plot.red_lines ? "да" : "нет"}
          </p>
          <textarea
            className="mt-3 w-full border border-ink/15 px-3 py-2 text-sm"
            rows={2}
            placeholder={m.commentPh}
            value={notes[plot.id] ?? ""}
            onChange={(e) => setNotes((n) => ({ ...n, [plot.id]: e.target.value }))}
          />
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <button type="button" disabled={actionLock.pending} onClick={() => void act(plot.id, "approve")} className="min-h-11 bg-pine px-3 py-1.5 text-paper disabled:opacity-50">
              {m.approve}
            </button>
            <button type="button" disabled={actionLock.pending} onClick={() => void act(plot.id, "revision")} className="min-h-11 border border-ink/20 px-3 py-1.5 disabled:opacity-50">
              {m.revision}
            </button>
            <button type="button" disabled={actionLock.pending} onClick={() => void act(plot.id, "reject")} className="min-h-11 px-3 py-1.5 text-clay disabled:opacity-50">
              {m.reject}
            </button>
          </div>
        </div>
      ))
        : null}
      <PageNav
        page={paged.page}
        pages={paged.pages}
        status={m.pageStatus.replace("{page}", String(paged.page + 1)).replace("{pages}", String(paged.pages))}
        prevLabel={m.pagePrev}
        nextLabel={m.pageNext}
        onPage={paged.setPage}
      />
    </div>
  );
}
