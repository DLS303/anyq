"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { fetchSiteBundle, postSite } from "@/lib/api";
import { money } from "@/lib/format";
import { t } from "@/i18n/messages";
import dynamic from "next/dynamic";
import type { Locale, ScheduleTask } from "@/lib/types";

const InteractiveGantt = dynamic(
  () => import("./InteractiveGantt").then((m) => m.InteractiveGantt),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center p-12 text-ink/50 glass rounded-2xl">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-pine mr-3" />
        Загрузка интерактивного графика Ганта...
      </div>
    ),
  }
);

const Bim3dViewer = dynamic(
  () => import("./Bim3dViewer").then((m) => m.Bim3dViewer),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center p-12 text-ink/50 glass rounded-2xl">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-pine mr-3" />
        Загрузка 3D модели (демо / иллюстративная модель)...
      </div>
    ),
  }
);

const KsActGenerator = dynamic(
  () => import("./KsActGenerator").then((m) => m.KsActGenerator),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center p-12 text-ink/50 glass rounded-2xl">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-pine mr-3" />
        Загрузка генератора актов КС-2 / КС-3...
      </div>
    ),
  }
);

type Tab =
  | "home"
  | "daily"
  | "rfi"
  | "sub"
  | "punch"
  | "qa"
  | "draw"
  | "gantt"
  | "money"
  | "crew"
  | "meet"
  | "dir"
  | "ks";

const TABS: { id: Tab; ru: string; kk: string }[] = [
  { id: "home", ru: "Обзор", kk: "Шолу" },
  { id: "daily", ru: "Журнал", kk: "Журнал" },
  { id: "rfi", ru: "RFI", kk: "RFI" },
  { id: "sub", ru: "Согласования", kk: "Келісім" },
  { id: "punch", ru: "Дефекты", kk: "Ақау" },
  { id: "qa", ru: "Качество / ТБ", kk: "Сапа / ЕҚ" },
  { id: "draw", ru: "Чертежи", kk: "Сызба" },
  { id: "gantt", ru: "График", kk: "График" },
  { id: "money", ru: "Бюджет", kk: "Бюджет" },
  { id: "crew", ru: "Табель", kk: "Табель" },
  { id: "meet", ru: "Совещания", kk: "Жиын" },
  { id: "dir", ru: "Команда", kk: "Команда" },
  { id: "ks", ru: "КС-2/КС-3", kk: "КС-2/КС-3" },
];

export function ProjectHub({ locale, id }: { locale: Locale; id: string }) {
  const m = t(locale);
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("home");
  const [bundle, setBundle] = useState<Record<string, unknown> | null>(null);
  const email = user?.email || "";

  function load() {
    fetchSiteBundle(id).then(setBundle).catch(() => setBundle(null));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!bundle) return <p className="text-ink/50">{m.empty}</p>;

  const snap = bundle.snapshot as {
    project: { title: string; address: string; id: string; plot_id?: string };
    health: string;
    budget_kzt: number;
    committed_kzt: number;
    actual_kzt: number;
    open_rfi: number;
    open_punch: number;
    open_incidents: number;
    fail_inspections: number;
  };
  const p = snap.project;
  const healthColor = snap.health === "green" ? "bg-pine" : snap.health === "red" ? "bg-clay" : "bg-sand";

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <p className="text-[11px] uppercase tracking-wider text-ink/45">Procore-style · field + office</p>
          <h1 className="text-2xl sm:text-4xl font-medium tracking-tight mt-1">{p.title}</h1>
          <p className="text-ink/60 mt-1">{p.address}</p>
        </div>
        <div className={`${healthColor} text-paper px-3 py-2 text-xs uppercase tracking-wider`}>health {snap.health}</div>
      </div>

      <div className="tab-scroll -mx-4 px-4 mb-6 border-b border-ink/10 pb-2">
        {TABS.map((x) => (
          <button
            key={x.id}
            type="button"
            onClick={() => setTab(x.id)}
            className={`shrink-0 min-h-11 px-3 rounded-full text-xs ${tab === x.id ? "bg-pine text-paper" : "text-ink/60"}`}
          >
            {locale === "kk" ? x.kk : x.ru}
          </button>
        ))}
      </div>

      {tab === "home" ? (
        <div className="grid sm:grid-cols-4 gap-3">
          <Kpi label="бюджет" value={money(snap.budget_kzt, locale)} />
          <Kpi label="обязательства" value={money(snap.committed_kzt, locale)} />
          <Kpi label="факт" value={money(snap.actual_kzt, locale)} />
          <Kpi label="open RFI / punch / ТБ" value={`${snap.open_rfi} / ${snap.open_punch} / ${snap.open_incidents}`} />

        </div>
      ) : null}

      {tab === "daily" ? (
        <Tool
          title="Daily log"
          items={bundle.daily as { id: string; day: string; weather: string; workers: number; notes: string; delays: string }[]}
          render={(x) => (
            <p>
              {x.day} · {x.weather} · {x.workers} чел. — {x.notes}
              {x.delays ? ` · простой: ${x.delays}` : ""}
            </p>
          )}
        >
          {user ? (
            <form
              className="grid sm:grid-cols-2 gap-2 mb-4"
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                await postSite(`projects/${p.id}/daily`, email, {
                  day: String(fd.get("day")),
                  workers: Number(fd.get("workers") || 0),
                  notes: String(fd.get("notes") || ""),
                  delays: String(fd.get("delays") || ""),
                  weather: "clear",
                });
                load();
                e.currentTarget.reset();
              }}
            >
              <input name="day" type="date" required className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="workers" type="number" placeholder="люди" className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="notes" placeholder="работы" className="border border-ink/15 px-2 py-1 text-sm sm:col-span-2" />
              <button className="bg-pine text-paper py-1 text-sm">+ журнал</button>
            </form>
          ) : null}
        </Tool>
      ) : null}

      {tab === "rfi" ? (
        <Tool
          title="RFI"
          items={bundle.rfis as { id: string; number: string; title: string; question: string; answer: string; status: string; drawing: string }[]}
          render={(x) => (
            <div>
              <p className="font-medium">
                {x.number} · {x.title} · {x.status}
                {x.drawing ? ` · ${x.drawing}` : ""}
              </p>
              <p className="text-ink/60">{x.question}</p>
              {x.answer ? <p className="mt-1">A: {x.answer}</p> : user ? (
                <button
                  type="button"
                  className="underline text-xs mt-1"
                  onClick={async () => {
                    const answer = prompt("Ответ") || "";
                    if (!answer) return;
                    await postSite(`rfis/${x.id}/answer`, email, { answer });
                    load();
                  }}
                >
                  ответить
                </button>
              ) : null}
            </div>
          )}
        >
          {user ? (
            <form
              className="grid gap-2 mb-4"
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                await postSite(`projects/${p.id}/rfis`, email, {
                  title: String(fd.get("title")),
                  question: String(fd.get("question")),
                  drawing: String(fd.get("drawing") || ""),
                });
                load();
                e.currentTarget.reset();
              }}
            >
              <input name="title" required placeholder="тема" className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="drawing" placeholder="лист АР/КЖ" className="border border-ink/15 px-2 py-1 text-sm" />
              <textarea name="question" required placeholder="вопрос площадки" className="border border-ink/15 px-2 py-1 text-sm" />
              <button className="bg-pine text-paper py-1 text-sm">+ RFI</button>
            </form>
          ) : null}
        </Tool>
      ) : null}

      {tab === "sub" ? (
        <Tool
          title="Submittals"
          items={bundle.submittals as { id: string; number: string; title: string; spec_section: string; status: string; vendor: string }[]}
          render={(x) => (
            <p>
              {x.number} · {x.title} · {x.spec_section} · {x.vendor} · {x.status}
            </p>
          )}
        />
      ) : null}

      {tab === "punch" ? (
        <Tool
          title="Punch list"
          items={bundle.punches as { id: string; title: string; location: string; trade: string; status: string }[]}
          render={(x) => (
            <div className="flex justify-between gap-3">
              <p>
                {x.title} · {x.location} · {x.trade} · {x.status}
              </p>
              {user && x.status !== "closed" ? (
                <button
                  type="button"
                  className="underline text-xs"
                  onClick={async () => {
                    await postSite(`punches/${x.id}/status`, email, { status: x.status === "open" ? "ready" : "closed" });
                    load();
                  }}
                >
                  {x.status === "open" ? "готово" : "закрыть"}
                </button>
              ) : null}
            </div>
          )}
        >
          {user ? (
            <form
              className="grid sm:grid-cols-3 gap-2 mb-4"
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                await postSite(`projects/${p.id}/punches`, email, {
                  title: String(fd.get("title")),
                  location: String(fd.get("location") || ""),
                  trade: String(fd.get("trade") || ""),
                });
                load();
                e.currentTarget.reset();
              }}
            >
              <input name="title" required placeholder="дефект" className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="location" placeholder="место" className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="trade" placeholder="подряд" className="border border-ink/15 px-2 py-1 text-sm" />
              <button className="bg-pine text-paper py-1 text-sm">+ punch</button>
            </form>
          ) : null}
        </Tool>
      ) : null}

      {tab === "qa" ? (
        <div className="grid md:grid-cols-2 gap-6">
          <Tool
            title="Inspections"
            items={bundle.inspections as { id: string; title: string; result: string; inspector: string; notes: string; day: string }[]}
            render={(x) => (
              <p>
                {x.day} · {x.title} · {x.result} · {x.inspector}
                {x.notes ? ` — ${x.notes}` : ""}
              </p>
            )}
          />
          <Tool
            title="Incidents"
            items={bundle.incidents as { id: string; title: string; severity: string; description: string; closed: boolean }[]}
            render={(x) => (
              <div className="flex justify-between gap-2">
                <p>
                  {x.title} · {x.severity} — {x.description}
                  {x.closed ? " · closed" : ""}
                </p>
                {user && !x.closed ? (
                  <button type="button" className="underline text-xs" onClick={async () => { await postSite(`incidents/${x.id}/close`, email, {}); load(); }}>
                    закрыть
                  </button>
                ) : null}
              </div>
            )}
          />
        </div>
      ) : null}

      {tab === "draw" ? (
        <Bim3dViewer
          locale={locale}
          drawings={
            (bundle.drawings as {
              id: string;
              code: string;
              title: string;
              revision: string;
              current: boolean;
              file?: string;
            }[]) || []
          }
          projectId={p.id}
          projectTitle={p.title}
        />
      ) : null}

      {tab === "gantt" ? (
        <InteractiveGantt
          locale={locale}
          projectId={p.id}
          schedule={(bundle.schedule as ScheduleTask[]) || []}
          email={email}
          onReload={load}
        />
      ) : null}

      {tab === "money" ? (
        <div className="grid gap-6">
          <Tool
            title="Budget vs committed vs actual"
            items={bundle.budget as { id: string; code: string; title: string; budget_kzt: number; committed_kzt: number; actual_kzt: number }[]}
            render={(x) => (
              <p>
                {x.code} {x.title} · план {money(x.budget_kzt, locale)} · обязательства {money(x.committed_kzt, locale)} · факт {money(x.actual_kzt, locale)}
              </p>
            )}
          />
          <Tool
            title="Change orders"
            items={bundle.changes as { id: string; number: string; title: string; amount_kzt: number; status: string }[]}
            render={(x) => (
              <div className="flex justify-between">
                <p>
                  {x.number} · {x.title} · {money(x.amount_kzt, locale)} · {x.status}
                </p>
                {user && x.status === "submitted" ? (
                  <button type="button" className="underline text-xs" onClick={async () => { await postSite(`changes/${x.id}/status`, email, { status: "approved" }); load(); }}>
                    approve
                  </button>
                ) : null}
              </div>
            )}
          />
        </div>
      ) : null}

      {tab === "crew" ? (
        <Tool
          title="Timesheets"
          items={bundle.timesheets as { id: string; day: string; crew: string; hours: number; cost_kzt: number }[]}
          render={(x) => (
            <p>
              {x.day} · {x.crew} · {x.hours} ч · {money(x.cost_kzt, locale)}
            </p>
          )}
        >
          {user ? (
            <form
              className="grid sm:grid-cols-4 gap-2 mb-4"
              onSubmit={async (e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                await postSite(`projects/${p.id}/timesheets`, email, {
                  day: String(fd.get("day")),
                  crew: String(fd.get("crew")),
                  hours: Number(fd.get("hours") || 0),
                  cost_kzt: Number(fd.get("cost") || 0),
                });
                load();
                e.currentTarget.reset();
              }}
            >
              <input name="day" type="date" required className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="crew" placeholder="бригада" className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="hours" type="number" placeholder="часы" className="border border-ink/15 px-2 py-1 text-sm" />
              <input name="cost" type="number" placeholder="₸" className="border border-ink/15 px-2 py-1 text-sm" />
              <button className="bg-pine text-paper py-1 text-sm">+ табель</button>
            </form>
          ) : null}
        </Tool>
      ) : null}

      {tab === "meet" ? (
        <Tool
          title="Meetings"
          items={bundle.meetings as { id: string; title: string; day: string; attendees: string; decisions: string }[]}
          render={(x) => (
            <p>
              {x.day} · {x.title} — {x.decisions} ({x.attendees})
            </p>
          )}
        />
      ) : null}

      {tab === "dir" ? (
        <Tool
          title="Directory"
          items={bundle.directory as { id: string; company: string; role_on_site: string }[]}
          render={(x) => (
            <p>
              {x.role_on_site} · {x.company}
            </p>
          )}
        />
      ) : null}

      {tab === "ks" ? (
        <KsActGenerator
          locale={locale}
          projectId={p.id}
          projectTitle={p.title}
          projectAddress={p.address}
          budget={
            (bundle.budget as {
              id: string;
              code: string;
              title: string;
              budget_kzt: number;
              committed_kzt: number;
              actual_kzt: number;
            }[]) || []
          }
        />
      ) : null}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-ink/10 bg-white/50 p-4">
      <p className="text-[11px] uppercase tracking-wider text-ink/45">{label}</p>
      <p className="font-serif text-2xl mt-1">{value}</p>
    </div>
  );
}

function Tool<T extends { id: string }>({
  title,
  items,
  render,
  children,
}: {
  title: string;
  items: T[];
  render: (item: T) => React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="font-serif text-2xl mb-3">{title}</h2>
      {children}
      <div className="grid gap-2">
        {(items || []).map((item) => (
          <div key={item.id} className="border border-ink/10 p-3 text-sm bg-white/40">
            {render(item)}
          </div>
        ))}
      </div>
    </section>
  );
}
