"use client";

import { useEffect, useRef, useState } from "react";
import { AuthImage } from "@/components/media/AuthImage";
import { t } from "@/i18n/messages";
import { deleteSite, postSite, uploadDailyPhotos } from "@/lib/api";
import { roleLabel, shareText, todayAlmaty, weatherLabel } from "@/lib/report";
import { toast } from "@/lib/toast";
import type { Locale } from "@/lib/types";

const MAX_PHOTOS = 10;
const MAX_BYTES = 10 * 1024 * 1024;

type Photo = { original_url: string; has_people?: boolean; has_plates?: boolean };
export type DailyEntry = {
  id: string;
  day: string;
  weather: string;
  temp_c?: number;
  workers: number;
  notes: string;
  delays: string;
  delay_hours?: number;
  author_role?: string;
  photos?: Photo[];
  share_active?: boolean;
  share_expires_at?: string | null;
};

const field = "w-full min-h-12 border border-ink/15 bg-white px-3 py-2 text-sm";
const button =
  "inline-flex min-h-12 w-full items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50 sm:w-auto";
const quiet =
  "inline-flex min-h-12 w-full items-center justify-center rounded-full border border-ink/20 bg-white px-4 text-sm font-medium disabled:opacity-50 sm:w-auto";

function formatUntil(iso: string, locale: Locale) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale === "kk" ? "kk-KZ" : "ru-KZ", {
    timeZone: "Asia/Almaty",
    dateStyle: "medium",
  }).format(date);
}

export function DailyReport({
  locale,
  projectId,
  logs,
  canWrite,
  startOpen,
  onLogin,
  onChange,
}: {
  locale: Locale;
  projectId: string;
  logs: DailyEntry[];
  canWrite: boolean;
  startOpen: boolean;
  onLogin: () => void;
  onChange: () => void;
}) {
  const m = t(locale);
  const [open, setOpen] = useState(startOpen);
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [days, setDays] = useState<Record<string, number>>({});
  const [links, setLinks] = useState<Record<string, string>>({});
  const [faceNote, setFaceNote] = useState(false);
  const lock = useRef(false);

  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [files]);

  function addFiles(list: FileList | null) {
    const picked = Array.from(list || []);
    const next = [...files];
    for (const file of picked) {
      if (file.size > MAX_BYTES) {
        toast(m.reportTooLarge);
        continue;
      }
      if (next.length >= MAX_PHOTOS) {
        toast(m.reportTooMany);
        break;
      }
      next.push(file);
    }
    setFiles(next);
  }

  async function save(form: HTMLFormElement) {
    if (lock.current) return;
    lock.current = true;
    const fd = new FormData(form);
    const key = crypto.randomUUID();
    setBusy(true);
    try {
      const created = (await postSite(
        `projects/${projectId}/daily`,
        "",
        {
          day: String(fd.get("day") || todayAlmaty()),
          workers: Number(fd.get("workers") || 0),
          notes: String(fd.get("notes") || ""),
          delays: String(fd.get("delays") || ""),
          delay_hours: Number(fd.get("delay_hours") || 0),
          weather: String(fd.get("weather") || "clear"),
          temp_c: Number(fd.get("temp_c") || 20),
        },
        key,
      )) as { id: string };
      if (files.length) {
        const uploaded = await uploadDailyPhotos(created.id, files);
        if (uploaded.added.some((item) => item.has_people)) {
          const key = `anyq-face-notice:${projectId}`;
          if (!window.localStorage.getItem(key)) {
            window.localStorage.setItem(key, "1");
            setFaceNote(true);
          }
        }
      }
      form.reset();
      setFiles([]);
      setOpen(true);
      toast(m.hubSaved);
      onChange();
    } catch (err) {
      toast(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function share(log: DailyEntry) {
    const chosen = days[log.id] ?? 30;
    setBusy(true);
    try {
      const data = (await postSite(`daily/${log.id}/share`, "", { expires_in_days: chosen })) as {
        token: string | null;
        expires_at: string | null;
        active: boolean;
      };
      if (!data.token) {
        toast(m.reportShareExists);
        onChange();
        return;
      }
      const url = `${window.location.origin}/${locale}/r/daily/${data.token}`;
      setLinks((prev) => ({ ...prev, [log.id]: url }));
      onChange();
    } catch (err) {
      toast(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(log: DailyEntry) {
    setBusy(true);
    try {
      await deleteSite(`daily/${log.id}/share`);
      setLinks((prev) => {
        const next = { ...prev };
        delete next[log.id];
        return next;
      });
      onChange();
    } catch (err) {
      toast(err instanceof Error ? err.message : m.hubSaveError);
    } finally {
      setBusy(false);
    }
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      toast(m.reportCopied);
    } catch {
      toast(m.reportCopy);
    }
  }

  if (!open && logs.length === 0) {
    return (
      <div className="border border-ink/10 bg-white/50 p-6 text-center">
        <p className="text-sm text-ink/70">{m.hubTodayEmpty}</p>
        <div className="mt-4 flex justify-center">
          <button type="button" className={button} onClick={() => (canWrite ? setOpen(true) : onLogin())}>
            {canWrite ? m.hubTodayAction : m.hubLogin}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid min-w-0 gap-4">
      {faceNote ? (
        <p className="border border-ink/15 bg-white/70 p-3 text-sm" role="status">
          {m.reportFaces}
        </p>
      ) : null}
      {canWrite ? (
        <form
          className="grid min-w-0 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void save(e.currentTarget);
          }}
        >
          <input name="day" type="date" required defaultValue={todayAlmaty()} className={field} />
          <div className="grid gap-2 sm:grid-cols-3">
            <select name="weather" defaultValue="clear" className={field} aria-label={m.reportWeather}>
              <option value="clear">{m.weatherClear}</option>
              <option value="cloud">{m.weatherCloud}</option>
              <option value="rain">{m.weatherRain}</option>
              <option value="snow">{m.weatherSnow}</option>
              <option value="wind">{m.weatherWind}</option>
            </select>
            <input name="temp_c" type="number" defaultValue={20} className={field} aria-label={m.reportTemp} />
            <input name="workers" type="number" min={0} placeholder={m.hubWorkers} className={field} />
          </div>
          <textarea name="notes" placeholder={m.hubWorkNotes} className={`${field} min-h-24`} />
          <div className="grid gap-2 sm:grid-cols-2">
            <input name="delays" placeholder={m.hubDelayReason} aria-label={m.reportDelaysLabel} className={field} />
            <input
              name="delay_hours"
              type="number"
              min={0}
              max={24}
              step="0.5"
              placeholder={m.hubDelayHours}
              aria-label={m.hubDelayHours}
              className={field}
            />
          </div>
          <p className="text-xs text-ink/50">{m.reportNoNames}</p>
          <label className={`${quiet} cursor-pointer`}>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,image/*"
              capture="environment"
              multiple
              className="sr-only"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
            {m.reportAddPhotos}
          </label>
          {previews.length ? (
            <div className="grid grid-cols-3 gap-2">
              {previews.map((src, index) => (
                <div key={src} className="relative min-w-0">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={src} alt="" className="aspect-square w-full object-cover" />
                  <button
                    type="button"
                    className="mt-1 inline-flex min-h-12 w-full items-center justify-center text-xs underline"
                    onClick={() => setFiles((prev) => prev.filter((_, i) => i !== index))}
                  >
                    {m.hubCloseItem}
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          <button className={button} disabled={busy}>
            {m.hubTodayAction}
          </button>
        </form>
      ) : null}
      <div className="grid gap-3">
        {logs.map((log) => {
          const link = links[log.id];
          const message = link ? shareText(m, log.day, link) : "";
          return (
            <article key={log.id} className="min-w-0 border border-ink/10 bg-white/40 p-3 text-sm">
              <p>
                {log.day} · {weatherLabel(log.weather, m)}
                {typeof log.temp_c === "number" ? ` · ${log.temp_c}°` : ""} · {log.workers} {m.hubWorkers}
              </p>
              {log.notes ? <p className="mt-1">{log.notes}</p> : null}
              {log.delays || log.delay_hours ? (
                <p className="mt-1 text-ink/60">
                  {m.reportDelaysLabel}: {log.delays}
                  {log.delay_hours ? ` · ${log.delay_hours} ${m.hubHours}` : ""}
                </p>
              ) : null}
              {log.author_role ? (
                <p className="mt-1 text-ink/50">
                  {m.reportAuthor}: {roleLabel(log.author_role, m)}
                </p>
              ) : null}
              {log.photos?.length ? (
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {log.photos.map((photo) => (
                    <AuthImage
                      key={photo.original_url}
                      src={photo.original_url}
                      alt={m.reportPhotoAlt}
                      className="aspect-square w-full object-cover"
                    />
                  ))}
                </div>
              ) : null}
              {canWrite ? (
                <div className="mt-3 grid gap-2">
                  <label className="grid gap-1 text-xs text-ink/60">
                    {m.reportExpires}
                    <input
                      type="number"
                      min={14}
                      max={90}
                      step={1}
                      value={days[log.id] ?? 30}
                      aria-describedby={`share-days-${log.id}`}
                      className={field}
                      onChange={(e) => setDays((prev) => ({ ...prev, [log.id]: Number(e.target.value) }))}
                    />
                    <span id={`share-days-${log.id}`}>{m.reportExpiresHint}</span>
                  </label>
                  {log.share_active && log.share_expires_at ? (
                    <p>{m.reportActiveUntil.replace("{date}", formatUntil(log.share_expires_at, locale))}</p>
                  ) : null}
                  <div className="grid gap-2 sm:flex sm:flex-wrap">
                    <button type="button" className={button} disabled={busy} onClick={() => void share(log)}>
                      {m.reportShare}
                    </button>
                    {log.share_active || link ? (
                      <button type="button" className={quiet} disabled={busy} onClick={() => void revoke(log)}>
                        {m.reportRevoke}
                      </button>
                    ) : null}
                  </div>
                  {link ? (
                    <div className="grid gap-2">
                      <input readOnly value={link} className={`${field} text-xs`} />
                      <div className="grid gap-2 sm:flex sm:flex-wrap">
                        <button type="button" className={quiet} onClick={() => void copy(link)}>
                          {m.reportCopy}
                        </button>
                        <a className={button} href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer">
                          {m.reportWhatsApp}
                        </a>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
