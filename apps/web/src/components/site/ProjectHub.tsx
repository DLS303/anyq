"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { addProjectMember, fetchSiteBundle, postSite, removeProjectMember } from "@/lib/api";
import { money } from "@/lib/format";
import { canEditProject, PILOT_MODE } from "@/lib/pilot";
import { siteRoleLabel, statusLabel } from "@/lib/report";
import { ErrorRetry, LoadingSkeleton, isMissing, useAsync, useGuardedSubmit } from "@/lib/useAsync";
import { AuthImage } from "@/components/media/AuthImage";
import { DailyReport, type DailyEntry } from "./DailyReport";
import { InspectionForm } from "./InspectionForm";
import { MeetingForm } from "./MeetingForm";
import { toast } from "@/lib/toast";
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

const ProcurementTab = dynamic(
  () => import("./ProcurementTab").then((m) => m.ProcurementTab),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center p-12 text-ink/50 glass rounded-2xl">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-pine mr-3" />
      </div>
    ),
  },
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
  | "today"
  | "daily"
  | "rfi"
  | "sub"
  | "punch"
  | "procurement"
  | "qa"
  | "draw"
  | "gantt"
  | "money"
  | "crew"
  | "meet"
  | "dir"
  | "ks";

type Msg = ReturnType<typeof t>;

const LEGACY_TABS: Tab[] = [
  "home",
  "daily",
  "rfi",
  "sub",
  "punch",
  "qa",
  "draw",
  "gantt",
  "money",
  "crew",
  "meet",
  "dir",
  "ks",
];

const PILOT_MAIN: Tab[] = ["today", "punch", "procurement", "money", "gantt"];
const PILOT_MORE: Tab[] = ["rfi", "sub", "qa", "draw", "crew", "meet", "dir", "ks"];

function tabLabel(id: Tab, m: Msg, pilot: boolean) {
  switch (id) {
    case "home":
      return m.tabHome;
    case "today":
      return m.tabToday;
    case "daily":
      return m.tabDaily;
    case "rfi":
      return m.tabRfi;
    case "sub":
      return m.tabSub;
    case "punch":
      return pilot ? m.tabIssues : m.tabPunch;
    case "procurement":
      return m.tabBuy;
    case "qa":
      return m.tabQa;
    case "draw":
      return m.tabDraw;
    case "gantt":
      return m.tabGantt;
    case "money":
      return pilot ? m.tabMoneyName : m.tabBudget;
    case "crew":
      return m.tabCrew;
    case "meet":
      return m.tabMeet;
    case "dir":
      return m.tabDir;
    case "ks":
      return pilot ? m.tabAct : m.tabKs;
    default:
      return id;
  }
}

function directoryRole(role: string, m: Msg) {
  const labeled = siteRoleLabel(role, m);
  if (labeled === m.roleMember && role) return role;
  return labeled;
}

function healthLabel(health: string, m: Msg) {
  if (health === "green") return m.healthOk;
  if (health === "red") return m.healthBad;
  return m.healthWarn;
}

const primaryBtn =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";

export function ProjectHub({ locale, id }: { locale: Locale; id: string }) {
  const m = t(locale);
  const router = useRouter();
  const { user } = useAuth();
  const pilot = PILOT_MODE;
  const [tab, setTab] = useState<Tab>(pilot ? "today" : "home");
  const [showPunch, setShowPunch] = useState(false);
  const [showExtra, setShowExtra] = useState(false);
  const email = user?.email || "";
  const bundleQuery = useAsync(() => fetchSiteBundle(id), [id]);
  const bundle = bundleQuery.data;
  const load = bundleQuery.reload;
  const forms = useGuardedSubmit(m.hubSaved, m.hubSaveError, load);

  function goLogin() {
    router.push(`/${locale}/login`);
  }

  if (bundleQuery.loading || !bundle) {
    if (bundleQuery.status === "error") {
      if (isMissing(bundleQuery.error)) {
        return (
          <div className="border border-ink/10 bg-white/50 p-6 text-center">
            <h1 className="font-serif text-3xl">{m.hubNotFoundTitle}</h1>
            <p className="mt-2 text-sm text-ink/70">{m.hubNotFound}</p>
            <Link href={`/${locale}/site`} className={`${primaryBtn} mt-4`}>
              {m.hubBackToList}
            </Link>
          </div>
        );
      }
      return <ErrorRetry message={m.hubLoadError} retryLabel={m.hubRetry} onRetry={load} />;
    }
    return <LoadingSkeleton label={m.hubLoading} />;
  }

  const snap = bundle.snapshot as {
    project: {
      title: string;
      address: string;
      id: string;
      plot_id?: string;
      owner_id?: string | null;
      contractor_id?: string | null;
    };
    health: string;
    budget_kzt: number | null;
    committed_kzt: number;
    actual_kzt: number;
    open_rfi: number;
    open_punch: number;
    open_incidents: number;
    fail_inspections: number;
  };
  const p = snap.project;
  const directory = (bundle.directory as { user_id?: string }[]) || [];
  const canEdit = canEditProject(user, p, directory);
  const canApprove = Boolean(bundle.can_approve_changes);
  const healthColor = snap.health === "green" ? "bg-pine" : snap.health === "red" ? "bg-clay" : "bg-sand";
  const mainTabs = pilot ? PILOT_MAIN : LEGACY_TABS;
  const logs = (bundle.daily as DailyEntry[]) || [];
  const punches = (bundle.punches as { id: string; title: string; location: string; trade: string; status: string }[]) || [];
  const budget = (bundle.budget as { id: string; code: string; title: string; budget_kzt: number; committed_kzt: number; actual_kzt: number }[]) || [];
  const changes = (bundle.changes as { id: string; number: string; title: string; amount_kzt: number; status: string }[]) || [];

  function tabButton(id: Tab, className: string) {
    const on = tab === id;
    return (
      <button
        key={id}
        type="button"
        aria-current={on ? "page" : undefined}
        onClick={() => setTab(id)}
        className={className}
      >
        {tabLabel(id, m, pilot)}
      </button>
    );
  }

  return (
    <div className={pilot ? "min-w-0 max-w-full pb-24 sm:pb-0" : "min-w-0 max-w-full"}>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div className="min-w-0">
          <h1 className="text-2xl sm:text-4xl font-medium tracking-tight">{p.title}</h1>
          <p className="text-ink/60 mt-1">{p.address}</p>
        </div>
        <div className="flex items-center gap-2">
          {pilot ? (
            <div className="sm:hidden">
              <MoreMenu
                label={m.tabMore}
                active={PILOT_MORE.includes(tab)}
                items={PILOT_MORE.map((id) => ({ id, label: tabLabel(id, m, true) }))}
                onPick={setTab}
              />
            </div>
          ) : null}
          <div className={`${healthColor} text-paper px-3 py-2 text-xs uppercase tracking-wider`}>
            {healthLabel(snap.health, m)}
          </div>
        </div>
      </div>

      {pilot ? (
        <>
          <div className="hidden sm:flex sm:flex-wrap sm:gap-2 mb-6">
            {PILOT_MAIN.map((id) =>
              tabButton(
                id,
                `min-h-12 rounded-full px-3 text-sm ${tab === id ? "bg-pine text-paper" : "text-ink/70 hover:bg-white/70"}`,
              ),
            )}
            <MoreMenu
              label={m.tabMore}
              active={PILOT_MORE.includes(tab)}
              items={PILOT_MORE.map((id) => ({ id, label: tabLabel(id, m, true) }))}
              onPick={setTab}
            />
          </div>
          <nav
            className="sm:hidden fixed bottom-0 inset-x-0 z-40 grid grid-cols-5 overflow-hidden border-t border-slate-200/80 bg-white/95 backdrop-blur-md pb-[env(safe-area-inset-bottom)]"
            aria-label={m.navMenu}
          >
            {PILOT_MAIN.map((id) =>
              tabButton(
                id,
                `flex w-full min-w-0 flex-col items-center justify-center min-h-12 px-0.5 text-center text-[10px] leading-tight ${
                  tab === id ? "text-pine font-semibold" : "text-slate-500"
                }`,
              ),
            )}
          </nav>
        </>
      ) : (
        <div className="tab-scroll -mx-4 px-4 mb-6 border-b border-ink/10 pb-2">
          {mainTabs.map((id) =>
            tabButton(
              id,
              `shrink-0 min-h-11 px-3 rounded-full text-xs ${tab === id ? "bg-pine text-paper" : "text-ink/60"}`,
            ),
          )}
        </div>
      )}

      {tab === "home" ? (
        <div className="grid sm:grid-cols-4 gap-3">
          <Kpi label={m.tabBudget} value={snap.budget_kzt == null ? m.objectBudgetEmpty : money(snap.budget_kzt, locale)} />
          <Kpi label={m.hubCommitted} value={money(snap.committed_kzt, locale)} />
          <Kpi label={m.hubActual} value={money(snap.actual_kzt, locale)} />
          <Kpi
            label={`${m.hubIssueRfi} / ${m.hubIssuePunch} / ${m.hubIssueSafety}`}
            value={`${snap.open_rfi} / ${snap.open_punch} / ${snap.open_incidents}`}
          />
        </div>
      ) : null}

      {tab === "today" ? (
        <div className="grid gap-4">
          <div className="grid sm:grid-cols-2 gap-3">
            <Kpi label={m.hubHealth} value={healthLabel(snap.health, m)} />
            <Kpi label={m.hubOpenIssues} value={String(snap.open_punch + snap.open_rfi + snap.open_incidents)} />
          </div>
          <p className="text-sm text-ink/70">
            {snap.open_punch + snap.open_rfi + snap.open_incidents === 0
              ? m.hubNoOpen
              : `${m.hubIssuePunch} ${snap.open_punch} · ${m.hubIssueRfi} ${snap.open_rfi} · ${m.hubIssueSafety} ${snap.open_incidents}`}
          </p>
          <DailyReport
            locale={locale}
            projectId={p.id}
            logs={logs}
            canWrite={Boolean(user) && canEdit}
            onLogin={goLogin}
            onChange={load}
          />
        </div>
      ) : null}

      {tab === "daily" ? (
        <DailyReport
          locale={locale}
          projectId={p.id}
          logs={logs}
          canWrite={Boolean(user) && canEdit}
          onLogin={goLogin}
          onChange={load}
        />
      ) : null}

      {tab === "rfi" ? (
        <Tool
          title={m.tabRfi}
          empty={m.hubEmpty}
          items={bundle.rfis as { id: string; number: string; title: string; question: string; answer: string; status: string; drawing: string }[]}
          render={(x) => (
            <div>
              <p className="font-medium">
                {x.number} · {x.title} · {statusLabel(x.status, m)}
                {x.drawing ? ` · ${x.drawing}` : ""}
              </p>
              <p className="text-ink/60">{x.question}</p>
              {x.answer ? <p className="mt-1">{m.hubAnswerPrefix}: {x.answer}</p> : user ? (
                <button
                  type="button"
                  className="underline text-xs mt-1"
                  onClick={async () => {
                    const answer = prompt(m.hubAnswerPrefix) || "";
                    if (!answer) return;
                    try {
                      await postSite(`rfis/${x.id}/answer`, email, { answer });
                      toast(m.hubSaved);
                      load();
                    } catch (err) {
                      toast(err instanceof Error ? err.message : m.hubSaveError);
                    }
                  }}
                >
                  {m.hubAnswer}
                </button>
              ) : null}
            </div>
          )}
        >
          {user ? (
            <form
              className="grid gap-2 mb-4"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const fd = new FormData(form);
                void forms.submit(async (key) => {
                  await postSite(
                    `projects/${p.id}/rfis`,
                    email,
                    {
                      title: String(fd.get("title")),
                      question: String(fd.get("question")),
                      drawing: String(fd.get("drawing") || ""),
                    },
                    key,
                  );
                  return form;
                });
              }}
            >
              <input name="title" required placeholder={m.hubRfiTitle} className="border border-ink/15 px-2 py-1 text-sm min-h-12" />
              <input name="drawing" placeholder={m.hubRfiDrawing} className="border border-ink/15 px-2 py-1 text-sm min-h-12" />
              <textarea name="question" required placeholder={m.hubRfiQuestion} className="border border-ink/15 px-2 py-1 text-sm min-h-24" />
              <button className={primaryBtn} disabled={forms.submitting}>
                {m.tabRfi}
              </button>
            </form>
          ) : null}
        </Tool>
      ) : null}

      {tab === "sub" ? (
        <Tool
          title={m.tabSub}
          empty={m.hubEmpty}
          items={bundle.submittals as { id: string; number: string; title: string; spec_section: string; status: string; vendor: string }[]}
          render={(x) => (
            <p>
              {x.number} · {x.title} · {x.spec_section} · {x.vendor} · {statusLabel(x.status, m)}
            </p>
          )}
        />
      ) : null}

      {tab === "punch" ? (
        pilot && punches.length === 0 && !showPunch ? (
          <EmptyLine
            text={m.hubPunchEmpty}
            action={
              <button type="button" className={primaryBtn} onClick={() => (user ? setShowPunch(true) : goLogin())}>
                {user ? m.hubPunchAction : m.hubLogin}
              </button>
            }
          />
        ) : (
          <Tool
            title={m.tabIssues}
            empty={m.hubEmpty}
            items={punches}
            render={(x) => (
              <div className="flex justify-between gap-3">
                <p>
                  {x.title} · {x.location} · {x.trade} · {statusLabel(x.status, m)}
                </p>
                {user && canEdit && x.status !== "closed" ? (
                  <button
                    type="button"
                    className="underline text-xs"
                    onClick={async () => {
                      try {
                        await postSite(`punches/${x.id}/status`, email, { status: x.status === "open" ? "ready" : "closed" });
                        toast(m.hubSaved);
                        load();
                      } catch (err) {
                        toast(err instanceof Error ? err.message : m.hubSaveError);
                      }
                    }}
                  >
                    {x.status === "open" ? m.hubReady : m.hubCloseItem}
                  </button>
                ) : null}
              </div>
            )}
          >
            {user && (pilot ? canEdit : true) ? (
              <form
                className="grid sm:grid-cols-3 gap-2 mb-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const fd = new FormData(form);
                  void forms.submit(async (key) => {
                    await postSite(
                      `projects/${p.id}/punches`,
                      email,
                      {
                        title: String(fd.get("title")),
                        location: String(fd.get("location") || ""),
                        trade: String(fd.get("trade") || ""),
                      },
                      key,
                    );
                    return form;
                  });
                }}
              >
                <input name="title" required placeholder={m.tabIssues} className="border border-ink/15 px-2 py-1 text-sm min-h-12" />
                <input name="location" placeholder={m.hubPlace} className="border border-ink/15 px-2 py-1 text-sm min-h-12" />
                <input name="trade" placeholder={m.hubTrade} className="border border-ink/15 px-2 py-1 text-sm min-h-12" />
                <button className={primaryBtn} disabled={forms.submitting}>
                  {m.hubPunchAction}
                </button>
              </form>
            ) : null}
          </Tool>
        )
      ) : null}

      {tab === "procurement" ? <ProcurementTab locale={locale} projectId={p.id} projectTitle={p.title} /> : null}

      {tab === "qa" ? (
        <div className="grid md:grid-cols-2 gap-6">
          <Tool
            title={m.toolInspections}
            empty={m.hubEmpty}
            items={
              bundle.inspections as {
                id: string;
                title: string;
                result: string;
                inspector: string;
                notes: string;
                day: string;
                photo?: string;
                items?: { label: string; result: string; comment: string }[];
                checklist?: string[];
              }[]
            }
            render={(x) => (
              <div>
                <p>
                  {x.day} · {x.title} · {statusLabel(x.result, m)} · {x.inspector}
                </p>
                {(x.items?.length ? x.items : (x.checklist || []).map((label) => ({ label, result: "", comment: "" }))).map((item, index) => (
                  <p key={`${x.id}-${index}`} className="text-ink/70">
                    {item.label}
                    {item.result ? ` · ${statusLabel(item.result, m)}` : ""}
                    {item.comment ? ` — ${item.comment}` : ""}
                  </p>
                ))}
                {x.notes ? <p className="mt-1">{x.notes}</p> : null}
                {x.photo ? <AuthImage src={x.photo} alt={m.inspPhoto} className="mt-2 aspect-video w-full max-w-xs object-cover" /> : null}
              </div>
            )}
          >
            {user ? <InspectionForm locale={locale} projectId={p.id} onDone={load} /> : null}
          </Tool>
          <Tool
            title={m.toolIncidents}
            empty={m.hubEmpty}
            items={bundle.incidents as { id: string; title: string; severity: string; description: string; closed: boolean }[]}
            render={(x) => (
              <div className="flex justify-between gap-2">
                <p>
                  {x.title} · {statusLabel(x.severity, m)} — {x.description}
                  {x.closed ? ` · ${m.statusClosed}` : ""}
                </p>
                {user && !x.closed ? (
                  <button
                    type="button"
                    className="underline text-xs"
                    onClick={async () => {
                      try {
                        await postSite(`incidents/${x.id}/close`, email, {});
                        toast(m.hubSaved);
                        load();
                      } catch (err) {
                        toast(err instanceof Error ? err.message : m.hubSaveError);
                      }
                    }}
                  >
                    {m.hubCloseItem}
                  </button>
                ) : null}
              </div>
            )}
          >
            {user ? (
              <form
                className="mb-4 grid gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const fd = new FormData(form);
                  void forms.submit(async (key) => {
                    await postSite(
                      `projects/${p.id}/incidents`,
                      email,
                      {
                        title: String(fd.get("title") || ""),
                        severity: String(fd.get("severity") || "low"),
                        description: String(fd.get("description") || ""),
                        day: String(fd.get("day") || ""),
                      },
                      key,
                    );
                    return form;
                  });
                }}
              >
                <input name="title" required placeholder={m.toolIncidents} className="min-h-12 border border-ink/15 px-2 py-1 text-sm" />
                <select name="severity" className="min-h-12 border border-ink/15 px-2 py-1 text-sm" aria-label={m.toolIncidents}>
                  <option value="low">{m.statusLow}</option>
                  <option value="medium">{m.statusMedium}</option>
                  <option value="high">{m.statusHigh}</option>
                </select>
                <input name="day" type="date" className="min-h-12 border border-ink/15 px-2 py-1 text-sm" />
                <textarea name="description" className="min-h-24 border border-ink/15 px-2 py-1 text-sm" placeholder={m.inspNotes} />
                <button className={primaryBtn} disabled={forms.submitting}>
                  {m.toolIncidents}
                </button>
              </form>
            ) : null}
          </Tool>
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
        <div className="min-w-0 max-w-full">
          <InteractiveGantt
            locale={locale}
            projectId={p.id}
            schedule={(bundle.schedule as ScheduleTask[]) || []}
            email={email}
            canEdit={canEdit}
            pilotEmpty={pilot}
            emptyText={m.hubGanttEmpty}
            emptyAction={m.hubGanttAction}
            onNeedLogin={goLogin}
            onReload={load}
          />
        </div>
      ) : null}

      {tab === "money" ? (
        pilot && budget.length === 0 && changes.length === 0 && !showExtra ? (
          <EmptyLine
            text={m.hubMoneyEmpty}
            action={
              <button type="button" className={primaryBtn} onClick={() => (canEdit ? setShowExtra(true) : goLogin())}>
                {canEdit ? m.hubMoneyAction : m.hubLogin}
              </button>
            }
          />
        ) : (
          <div className="grid gap-6">
            {budget.length > 0 || !pilot ? (
              <Tool
                title={m.hubBudgetTitle}
                empty={m.hubEmpty}
                items={budget}
                render={(x) => (
                  <p>
                    {x.code} {x.title} · {m.hubPlan} {money(x.budget_kzt, locale)} · {m.hubCommitted} {money(x.committed_kzt, locale)} · {m.hubActual} {money(x.actual_kzt, locale)}
                  </p>
                )}
              />
            ) : null}
            {changes.length > 0 || !pilot || showExtra || canEdit ? (
              <Tool
                title={m.hubExtraTitle}
                empty={m.hubEmpty}
                items={changes}
                render={(x) => (
                  <div className="flex justify-between gap-3">
                    <p>
                      {x.number} · {x.title} · {money(x.amount_kzt, locale)} · {statusLabel(x.status, m)}
                    </p>
                    {canApprove && x.status === "submitted" ? (
                      <button
                        type="button"
                        className="underline text-xs min-h-12"
                        onClick={async () => {
                          try {
                            await postSite(`changes/${x.id}/status`, email, { status: "approved" });
                            toast(m.hubSaved);
                            load();
                          } catch (err) {
                            toast(err instanceof Error ? err.message : m.hubSaveError);
                          }
                        }}
                      >
                        {m.hubApprove}
                      </button>
                    ) : null}
                  </div>
                )}
              >
                {canEdit ? (
                  <form
                    className="grid sm:grid-cols-3 gap-2 mb-4"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const form = e.currentTarget;
                      const fd = new FormData(form);
                      void forms.submit(async (key) => {
                        await postSite(
                          `projects/${p.id}/changes`,
                          email,
                          {
                            title: String(fd.get("title")),
                            amount_kzt: Number(fd.get("amount") || 0),
                            reason: String(fd.get("reason") || ""),
                          },
                          key,
                        );
                        return form;
                      });
                    }}
                  >
                    <input name="title" required placeholder={m.hubExtraTitle} className="border border-ink/15 px-2 py-2 text-sm min-h-12" />
                    <input name="amount" required type="number" placeholder={m.hubAmount} className="border border-ink/15 px-2 py-2 text-sm min-h-12" />
                    <input name="reason" placeholder={m.hubReason} className="border border-ink/15 px-2 py-2 text-sm min-h-12" />
                    <button className={primaryBtn} disabled={forms.submitting}>
                      {m.hubMoneyAction}
                    </button>
                  </form>
                ) : null}
              </Tool>
            ) : null}
          </div>
        )
      ) : null}

      {tab === "crew" ? (
        <Tool
          title={m.tabCrew}
          empty={m.hubEmpty}
          items={bundle.timesheets as { id: string; day: string; crew: string; hours: number; cost_kzt: number }[]}
          render={(x) => (
            <p>
              {x.day} · {x.crew} · {x.hours} {m.hubHours} · {money(x.cost_kzt, locale)}
            </p>
          )}
        >
          {user ? (
            <form
              className="grid sm:grid-cols-4 gap-2 mb-4"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const fd = new FormData(form);
                void forms.submit(async (key) => {
                  await postSite(
                    `projects/${p.id}/timesheets`,
                    email,
                    {
                      day: String(fd.get("day")),
                      crew: String(fd.get("crew")),
                      hours: Number(fd.get("hours") || 0),
                      cost_kzt: Number(fd.get("cost") || 0),
                    },
                    key,
                  );
                  return form;
                });
              }}
            >
              <input name="day" type="date" required className="min-h-12 border border-ink/15 px-2 py-1 text-sm" />
              <input name="crew" placeholder={m.hubCrewName} className="min-h-12 border border-ink/15 px-2 py-1 text-sm" />
              <input name="hours" type="number" placeholder={m.hubHours} className="min-h-12 border border-ink/15 px-2 py-1 text-sm" />
              <input name="cost" type="number" placeholder="₸" className="min-h-12 border border-ink/15 px-2 py-1 text-sm" />
              <button className={primaryBtn} disabled={forms.submitting}>
                {m.tabCrew}
              </button>
            </form>
          ) : null}
        </Tool>
      ) : null}

      {tab === "meet" ? (
        <Tool
          title={m.toolMeetings}
          empty={m.hubEmpty}
          items={
            bundle.meetings as {
              id: string;
              title: string;
              day: string;
              attendees: string;
              decisions: string;
              agenda?: string;
              participants?: { role: string; name: string }[];
              decision_items?: { text: string; owner_role: string; due: string }[];
            }[]
          }
          render={(x) => (
            <div>
              <p className="font-medium">
                {x.day} · {x.title}
              </p>
              {x.agenda ? <p className="mt-1">{x.agenda}</p> : null}
              {x.participants?.length ? (
                <p className="mt-1 text-ink/70">
                  {x.participants.map((person) => `${siteRoleLabel(person.role, m)}${person.name ? ` (${person.name})` : ""}`).join(", ")}
                </p>
              ) : x.attendees ? (
                <p className="mt-1 text-ink/70">{x.attendees}</p>
              ) : null}
              {x.decision_items?.length
                ? x.decision_items.map((item, index) => (
                    <p key={`${x.id}-d-${index}`} className="mt-1">
                      {item.text} · {siteRoleLabel(item.owner_role, m)} · {item.due}
                    </p>
                  ))
                : x.decisions ? (
                    <p className="mt-1">{x.decisions}</p>
                  )
                : null}
            </div>
          )}
        >
          {user ? <MeetingForm locale={locale} projectId={p.id} onDone={load} /> : null}
        </Tool>
      ) : null}

      {tab === "dir" ? (
        <Tool
          title={m.tabDir}
          empty={m.hubEmpty}
          items={((bundle.members as { user_id: string; name: string; role: string; email: string }[]) || []).map((row) => ({
            ...row,
            id: row.user_id,
          }))}
          render={(x) => (
            <div className="flex items-center justify-between gap-3">
              <p>
                {directoryRole(x.role, m)} · {x.name}
                <span className="mt-1 block text-xs text-ink/50">{x.email}</span>
              </p>
              {bundle.can_manage_members ? (
                <button
                  type="button"
                  className="min-h-12 shrink-0 text-xs underline"
                  onClick={async () => {
                    try {
                      await removeProjectMember(p.id, x.user_id);
                      toast(m.hubSaved);
                      load();
                    } catch (err) {
                      toast(err instanceof Error ? err.message : m.hubSaveError);
                    }
                  }}
                >
                  {m.memberRemove}
                </button>
              ) : null}
            </div>
          )}
        >
          {bundle.can_manage_members ? (
            <form
              className="mb-4 grid gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const fd = new FormData(form);
                void forms.submit(async (key) => {
                  await addProjectMember(
                    p.id,
                    {
                      email: String(fd.get("email") || ""),
                      role: String(fd.get("role") || "foreman"),
                    },
                    key,
                  );
                  return form;
                });
              }}
            >
              <input name="email" type="email" required placeholder={m.memberEmail} className="min-h-12 border border-ink/15 px-2 py-1 text-sm" />
              <label className="grid gap-1 text-sm">
                {m.memberRole}
                <select name="role" defaultValue="foreman" className="min-h-12 border border-ink/15 bg-white px-2 text-sm">
                  <option value="foreman">{m.roleForeman}</option>
                  <option value="supervisor">{m.supervisor}</option>
                  <option value="procurement">{m.roleProcurement}</option>
                  <option value="customer">{m.roleCustomer}</option>
                </select>
              </label>
              <button className={primaryBtn} disabled={forms.submitting}>
                {m.memberAdd}
              </button>
            </form>
          ) : null}
        </Tool>
      ) : null}

      {tab === "ks" ? (
        <KsActGenerator
          locale={locale}
          projectId={p.id}
          projectTitle={p.title}
          projectAddress={p.address}
          budget={budget}
        />
      ) : null}
    </div>
  );
}

function EmptyLine({ text, action }: { text: string; action: React.ReactNode }) {
  return (
    <div className="border border-ink/10 bg-white/50 p-6 text-center">
      <p className="text-sm text-ink/70">{text}</p>
      <div className="mt-4 flex justify-center">{action}</div>
    </div>
  );
}

function MoreMenu({
  label,
  active,
  items,
  onPick,
}: {
  label: string;
  active: boolean;
  items: { id: Tab; label: string }[];
  onPick: (id: Tab) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
        className={`min-h-12 rounded-full px-3 text-sm ${active || open ? "bg-pine text-paper" : "text-ink/70 hover:bg-white/70"}`}
      >
        {label}
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 z-50 mt-1 min-w-44 rounded-xl border border-ink/10 bg-white py-1 shadow-lg">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className="block w-full min-h-12 px-3 text-left text-sm hover:bg-slate-50"
              onClick={() => {
                onPick(item.id);
                setOpen(false);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
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

function ItemList<T extends { id: string }>({
  items,
  empty,
  render,
}: {
  items: T[];
  empty: string;
  render: (item: T) => React.ReactNode;
}) {
  if (!items.length) return <p className="text-sm text-ink/50">{empty}</p>;
  return (
    <div className="grid gap-2">
      {items.map((item) => (
        <div key={item.id} className="border border-ink/10 p-3 text-sm bg-white/40">
          {render(item)}
        </div>
      ))}
    </div>
  );
}

function Tool<T extends { id: string }>({
  title,
  items,
  empty,
  render,
  children,
}: {
  title: string;
  items: T[];
  empty: string;
  render: (item: T) => React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="font-serif text-2xl mb-3">{title}</h2>
      {children}
      <ItemList items={items || []} empty={empty} render={render} />
    </section>
  );
}
