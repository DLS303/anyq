"use client";

import { useEffect, useRef, useState } from "react";
import { AuthAudio } from "@/components/media/AuthAudio";
import { AuthImage } from "@/components/media/AuthImage";
import { t } from "@/i18n/messages";
import { deleteSite, postSite, uploadDailyPhotos, uploadDailyVoice } from "@/lib/api";
import { roleLabel, shareText, todayAlmaty, weatherLabel } from "@/lib/report";
import { toast } from "@/lib/toast";
import type { Locale } from "@/lib/types";

const MAX_PHOTOS = 10;
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_VOICE_S = 120;

type Photo = { original_url: string; has_people?: boolean; has_plates?: boolean };
type Voice = { url: string; duration_s?: number };
export type DailyEntry = {
  id: string;
  day: string;
  weather: string;
  temp_c?: number | null;
  workers: number;
  notes: string;
  delays: string;
  delay_hours?: number;
  author_role?: string;
  photos?: Photo[];
  voice_notes?: Voice[];
  share_active?: boolean;
  share_expires_at?: string | null;
};

const WEATHER = [
  ["clear", "☀️"],
  ["cloud", "☁️"],
  ["rain", "🌧"],
  ["snow", "❄️"],
  ["wind", "💨"],
] as const;

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

function yesterdayAlmaty() {
  const [year, month, day] = todayAlmaty().split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function clock(total: number) {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function DailyReport({
  locale,
  projectId,
  logs,
  canWrite,
  onLogin,
  onChange,
}: {
  locale: Locale;
  projectId: string;
  logs: DailyEntry[];
  canWrite: boolean;
  onLogin: () => void;
  onChange: () => void;
}) {
  const m = t(locale);
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [weather, setWeather] = useState("");
  const [workers, setWorkers] = useState(0);
  const [notes, setNotes] = useState("");
  const [delays, setDelays] = useState("");
  const [delayHours, setDelayHours] = useState("");
  const [prefilled, setPrefilled] = useState(false);
  const [days, setDays] = useState<Record<string, number>>({});
  const [links, setLinks] = useState<Record<string, string>>({});
  const [faceNote, setFaceNote] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voice, setVoice] = useState<Blob | null>(null);
  const [voiceUrl, setVoiceUrl] = useState("");
  const [voiceSeconds, setVoiceSeconds] = useState(0);
  const lock = useRef(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [files]);

  function stopTimer() {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  }

  function stopRecorder() {
    stopTimer();
    const active = recorder.current;
    recorder.current = null;
    if (active && active.state !== "inactive") active.stop();
    setRecording(false);
  }

  function resetVoice() {
    stopRecorder();
    setVoice(null);
    setVoiceSeconds(0);
    setVoiceUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
  }

  function closeSheet() {
    resetVoice();
    setSheet(false);
  }

  function openSheet() {
    const previous = logs.find((log) => log.day === yesterdayAlmaty());
    if (previous) {
      setWeather(previous.weather || "");
      setWorkers(previous.workers || 0);
      setPrefilled(true);
    } else {
      setWeather("");
      setWorkers(0);
      setPrefilled(false);
    }
    setNotes("");
    setDelays("");
    setDelayHours("");
    setFiles([]);
    resetVoice();
    setSheet(true);
  }

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

  async function toggleVoice() {
    if (recording) {
      stopRecorder();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      toast(m.reportVoiceUnsupported);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = ["audio/webm", "audio/mp4", "audio/ogg"].find((item) => MediaRecorder.isTypeSupported(item)) || "";
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      rec.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      rec.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const type = rec.mimeType || mime || "audio/webm";
        const blob = new Blob(chunks.current, { type });
        setVoiceUrl((current) => {
          if (current) URL.revokeObjectURL(current);
          return URL.createObjectURL(blob);
        });
        setVoice(blob);
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
      setVoiceSeconds(0);
      const started = Date.now();
      timer.current = window.setInterval(() => {
        const elapsed = Math.min(MAX_VOICE_S, Math.round((Date.now() - started) / 1000));
        setVoiceSeconds(elapsed);
        if (elapsed >= MAX_VOICE_S) stopRecorder();
      }, 250);
    } catch {
      toast(m.reportVoiceUnsupported);
    }
  }

  async function save() {
    if (lock.current) return;
    if (!weather) {
      toast(m.reportWeatherNeed);
      return;
    }
    lock.current = true;
    const key = crypto.randomUUID();
    setBusy(true);
    try {
      const created = (await postSite(
        `projects/${projectId}/daily`,
        "",
        {
          day: todayAlmaty(),
          workers,
          notes,
          delays,
          delay_hours: Number(delayHours || 0),
          weather,
        },
        key,
      )) as { id: string };
      if (files.length) {
        const uploaded = await uploadDailyPhotos(created.id, files);
        if (uploaded.added.some((item) => item.has_people)) {
          const notice = `anyq-face-notice:${projectId}`;
          if (!window.localStorage.getItem(notice)) {
            window.localStorage.setItem(notice, "1");
            setFaceNote(true);
          }
        }
      }
      if (voice && voice.size) {
        await uploadDailyVoice(created.id, voice, voiceSeconds);
      }
      closeSheet();
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

  const weatherName = (code: string) => weatherLabel(code, m);

  return (
    <div className="grid min-w-0 gap-4">
      {faceNote ? (
        <p className="border border-ink/15 bg-white/70 p-3 text-sm" role="status">
          {m.reportFaces}
        </p>
      ) : null}
      {logs.length === 0 ? <p className="text-center text-sm text-ink/70">{m.hubTodayEmpty}</p> : null}
      <div className="flex justify-center">
        <button
          type="button"
          className="flex h-36 w-36 items-center justify-center rounded-full bg-pine px-4 text-center text-sm font-semibold leading-tight text-paper"
          onClick={() => (canWrite ? openSheet() : onLogin())}
        >
          {canWrite ? m.hubTodayAction : m.hubLogin}
        </button>
      </div>
      {sheet ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40" onClick={closeSheet}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="day-report-title"
            className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 id="day-report-title" className="text-lg font-medium">
                {m.hubTodayAction}
              </h2>
              <button type="button" className="min-h-12 px-2 text-sm underline" onClick={closeSheet}>
                {m.navClose}
              </button>
            </div>
            <p className="text-sm text-ink/60">{todayAlmaty()}</p>
            {prefilled ? <p className="mt-1 text-xs text-ink/50">{m.reportPrefilled}</p> : null}
            <div className="mt-3 grid grid-cols-5 gap-1" role="group" aria-label={m.reportWeather}>
              {WEATHER.map(([code, icon]) => (
                <button
                  key={code}
                  type="button"
                  aria-pressed={weather === code}
                  aria-label={weatherName(code)}
                  className={`min-h-12 rounded-2xl border text-lg ${weather === code ? "border-pine bg-pine/10" : "border-ink/15 bg-white"}`}
                  onClick={() => setWeather(code)}
                >
                  {icon}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="text-sm">{m.reportWorkers}</span>
              <div className="flex items-center gap-2">
                <button type="button" className="h-12 w-12 rounded-full border border-ink/20" onClick={() => setWorkers((value) => Math.max(0, value - 1))} aria-label="-">
                  −
                </button>
                <span className="w-8 text-center text-sm">{workers}</span>
                <button type="button" className="h-12 w-12 rounded-full border border-ink/20" onClick={() => setWorkers((value) => value + 1)} aria-label="+">
                  +
                </button>
              </div>
            </div>
            <label className="mt-3 grid gap-1 text-sm">
              {m.reportDid}
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className={`${field} min-h-24`} />
            </label>
            <p className="mt-1 text-xs text-ink/50">{m.reportNoNames}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <input value={delays} onChange={(event) => setDelays(event.target.value)} placeholder={m.hubDelayReason} aria-label={m.reportDelaysLabel} className={field} />
              <input
                value={delayHours}
                onChange={(event) => setDelayHours(event.target.value)}
                type="number"
                min={0}
                max={24}
                step="0.5"
                placeholder={m.hubDelayHours}
                aria-label={m.hubDelayHours}
                className={field}
              />
            </div>
            <label className={`${quiet} mt-3 cursor-pointer`}>
              <input
                type="file"
                accept="image/*"
                capture="environment"
                multiple
                className="sr-only"
                onChange={(event) => {
                  addFiles(event.target.files);
                  event.target.value = "";
                }}
              />
              {m.reportAddPhotos}
            </label>
            {previews.length ? (
              <div className="mt-2 grid grid-cols-3 gap-2">
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
            <div className="mt-3 grid gap-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm">{m.reportVoice}</span>
                <button type="button" className={quiet} onClick={() => void toggleVoice()}>
                  {recording ? `${m.reportVoiceStop} ${clock(voiceSeconds)}` : voice ? m.reportVoiceReady : m.reportVoiceStart}
                </button>
              </div>
              {voiceUrl && !recording ? <audio controls src={voiceUrl} className="w-full" aria-label={m.reportVoice} /> : null}
              {voice && !recording ? (
                <button type="button" className="min-h-12 text-left text-xs underline" onClick={resetVoice}>
                  {m.reportVoiceClear}
                </button>
              ) : null}
            </div>
            <button type="button" className={`${button} mt-4`} disabled={busy || recording} onClick={() => void save()}>
              {m.send}
            </button>
          </div>
        </div>
      ) : null}
      <div className="grid gap-3">
        {logs.map((log) => {
          const link = links[log.id];
          const message = link ? shareText(m, log.day, link) : "";
          return (
            <article key={log.id} className="min-w-0 border border-ink/10 bg-white/40 p-3 text-sm">
              <p>
                {log.day} · {weatherName(log.weather)}
                {typeof log.temp_c === "number" ? ` · ${log.temp_c}°` : ""} · {log.workers} {m.hubWorkers}
                {log.voice_notes?.length ? ` · ${m.reportVoiceMark}` : ""}
              </p>
              {log.notes ? <p className="mt-1 line-clamp-3">{log.notes}</p> : null}
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
                  {log.photos.slice(0, 3).map((photo) => (
                    <AuthImage
                      key={photo.original_url}
                      src={photo.original_url}
                      alt={m.reportPhotoAlt}
                      className="aspect-square w-full object-cover"
                    />
                  ))}
                </div>
              ) : null}
              {log.voice_notes?.map((note) => (
                <AuthAudio key={note.url} src={note.url} label={m.reportVoice} />
              ))}
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
                      onChange={(event) => setDays((prev) => ({ ...prev, [log.id]: Number(event.target.value) }))}
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
