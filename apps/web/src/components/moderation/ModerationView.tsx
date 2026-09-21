"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { fetchQueue, moderatePlot } from "@/lib/api";
import { titleOf } from "@/lib/format";
import type { Locale, Plot } from "@/lib/types";
import { t } from "@/i18n/messages";

export function ModerationView({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { user } = useAuth();
  const [plots, setPlots] = useState<Plot[]>([]);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});

  function load() {
    if (!user) return;
    fetchQueue(user.email)
      .then(setPlots)
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

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
    if (!user) return;
    await moderatePlot(user.email, id, action, notes[id] ?? "");
    load();
  }

  return (
    <div className="grid gap-4">
      {error ? <p className="text-clay text-sm">{error}</p> : null}
      {plots.length === 0 ? <p className="text-ink/50">{m.empty}</p> : null}
      {plots.map((plot) => (
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
          <div className="mt-3 flex gap-2 text-sm">
            <button onClick={() => act(plot.id, "approve")} className="bg-pine text-paper px-3 py-1.5">
              {m.approve}
            </button>
            <button onClick={() => act(plot.id, "revision")} className="border border-ink/20 px-3 py-1.5">
              {m.revision}
            </button>
            <button onClick={() => act(plot.id, "reject")} className="text-clay px-3 py-1.5">
              {m.reject}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
