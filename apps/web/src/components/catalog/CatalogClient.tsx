"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { PlotCard } from "@/components/plots/PlotCard";
import { WidgetBoundary } from "@/components/ui/WidgetBoundary";
import { PageNav, useServerPaged } from "@/components/ui/PagedList";
import { fetchPlots, fetchPlotsPage, saveSearch, suggestPlots } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PURPOSE } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";
import { ErrorRetry, LoadingSkeleton, useAsync, useSubmitLock } from "@/lib/useAsync";
import { DISTRICTS, type Locale, type Purpose } from "@/lib/types";
import { useMessages } from "@/lib/i18n";
import { loadWithin } from "@/lib/loadWithin";
import { ChunkFallback } from "@/components/ui/ChunkFallback";

const PlotMap = dynamic(() => loadWithin(import("./PlotMap")), {
  ssr: false,
  loading: () => <ChunkFallback />,
});

const PURPOSES = Object.keys(PURPOSE) as Purpose[];
const RADII = [0, 5, 10, 25, 50];

export function CatalogClient({ locale }: { locale: Locale }) {
  const m = useMessages();
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q, 300);
  const [purpose, setPurpose] = useState("");
  const [district, setDistrict] = useState("");
  const [verified, setVerified] = useState(false);
  const [gas, setGas] = useState(false);
  const [electricity, setElectricity] = useState(false);
  const [water, setWater] = useState(false);
  const [radius, setRadius] = useState(0);
  const [pick, setPick] = useState<[number, number] | null>(null);
  const [hints, setHints] = useState<{ kind: string; value: string; slug: string }[]>([]);
  const [saved, setSaved] = useState(false);
  const saveLock = useSubmitLock();

  const params = useMemo(
    () => ({
      q: debouncedQ || undefined,
      purpose: purpose || undefined,
      district: district || undefined,
      verified: verified ? "true" : undefined,
      gas: gas ? "connected" : undefined,
      electricity: electricity ? "connected" : undefined,
      water: water ? "connected" : undefined,
      lat: radius && pick ? String(pick[0]) : undefined,
      lng: radius && pick ? String(pick[1]) : undefined,
      radius_km: radius && pick ? String(radius) : undefined,
    }),
    [debouncedQ, purpose, district, verified, gas, electricity, water, radius, pick],
  );
  const query = useAsync((signal) => fetchPlots(params, signal), [params]);
  const plots = query.data ?? [];
  const paged = useServerPaged(JSON.stringify(params), (page, signal) => fetchPlotsPage(params, page, 24, signal));

  useEffect(() => {
    if (q.trim().length < 2) {
      setHints([]);
      return;
    }
    const controller = new AbortController();
    const tmr = window.setTimeout(() => {
      suggestPlots(q, controller.signal)
        .then((rows) => {
          if (!controller.signal.aborted) setHints(rows);
        })
        .catch(() => {
          if (!controller.signal.aborted) setHints([]);
        });
    }, 300);
    return () => {
      window.clearTimeout(tmr);
      controller.abort();
    };
  }, [q]);

  return (
    <div className="grid lg:grid-cols-[320px_1fr] gap-6">
      <aside className="glass rounded-frost p-5 h-fit">
        <h2 className="font-serif text-2xl mb-4">{m.filters}</h2>
        <label className="block text-xs uppercase tracking-wider text-ink/50">{m.search}</label>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={m.searchPh}
          className="mt-1 w-full border border-ink/15 bg-paper px-3 py-2 text-sm"
        />
        {hints.length > 0 ? (
          <ul className="border border-ink/10 bg-white text-sm mt-1">
            {hints.map((h) => (
              <li key={h.kind + h.value}>
                <button
                  type="button"
                  className="w-full text-left px-3 py-1.5 hover:bg-mist"
                  onClick={() => {
                    setQ(h.value);
                    setHints([]);
                  }}
                >
                  {h.value}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <label className="block text-xs uppercase tracking-wider text-ink/50 mt-4">{m.purpose}</label>
        <select
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
          className="mt-1 w-full border border-ink/15 bg-paper px-3 py-2 text-sm"
        >
          <option value="">{m.any}</option>
          {PURPOSES.map((p) => (
            <option key={p} value={p}>
              {PURPOSE[p][locale]}
            </option>
          ))}
        </select>
        <label className="block text-xs uppercase tracking-wider text-ink/50 mt-4">{m.district}</label>
        <select
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
          className="mt-1 w-full border border-ink/15 bg-paper px-3 py-2 text-sm"
        >
          <option value="">{m.any}</option>
          {DISTRICTS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
          {m.onlyVerified}
        </label>
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={gas} onChange={(e) => setGas(e.target.checked)} />
          {m.onlyGas}
        </label>
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={electricity} onChange={(e) => setElectricity(e.target.checked)} />
          {m.onlyLight}
        </label>
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={water} onChange={(e) => setWater(e.target.checked)} />
          {m.onlyWater}
        </label>
        <p className="text-xs uppercase tracking-wider text-ink/50 mt-4">{m.radius}</p>
        <p className="text-[11px] text-ink/40 mb-1">{m.pickOnMap}</p>
        <div className="flex flex-wrap gap-1">
          {RADII.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRadius(r)}
              className={`px-2 py-1 text-xs border ${radius === r ? "bg-pine text-paper border-pine" : "border-ink/15"}`}
            >
              {r === 0 ? m.any : `${r} ${m.km}`}
            </button>
          ))}
        </div>
        <button
          className="mt-4 text-sm underline text-ink/60"
          onClick={() => {
            setQ("");
            setPurpose("");
            setDistrict("");
            setVerified(false);
            setGas(false);
            setElectricity(false);
            setWater(false);
            setRadius(0);
            setPick(null);
          }}
        >
          {m.reset}
        </button>
        {user ? (
          <button
            type="button"
            className="mt-3 block min-h-11 text-sm underline disabled:opacity-50"
            disabled={saveLock.pending}
            onClick={() => {
              void saveLock.run(async () => {
                await saveSearch(user.email, q || district || m.search, params);
                setSaved(true);
              });
            }}
          >
            {saved ? m.saved : m.saveSearch}
          </button>
        ) : null}
      </aside>
      <div className="grid min-w-0 gap-4">
        <div className="h-[280px] overflow-hidden rounded-frost border border-ice/15 sm:h-[420px]">
          <WidgetBoundary message={m.widgetError} retryLabel={m.retry}>
            <PlotMap plots={plots} locale={locale} onPick={setPick} pick={pick} />
          </WidgetBoundary>
        </div>
        {paged.loading ? <LoadingSkeleton label={m.hubLoading} /> : null}
        {paged.status === "error" ? (
          <ErrorRetry message={m.listLoadError} retryLabel={m.retry} onRetry={paged.reload} />
        ) : null}
        {!paged.loading && paged.status !== "error" && paged.total === 0 ? (
          <p className="text-ink/60">{m.empty}</p>
        ) : null}
        {paged.status !== "error" && paged.slice.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {paged.slice.map((plot) => (
              <PlotCard key={plot.id} plot={plot} locale={locale} />
            ))}
          </div>
        ) : null}
        <PageNav
          page={paged.page}
          pages={paged.pages}
          status={m.pageStatus.replace("{page}", String(paged.page + 1)).replace("{pages}", String(paged.pages))}
          prevLabel={m.pagePrev}
          nextLabel={m.pageNext}
          onPage={paged.setPage}
        />
      </div>
    </div>
  );
}
