"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthImage } from "@/components/media/AuthImage";
import { t } from "@/i18n/messages";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  createPunchItem,
  fetchPunchItems,
  fetchPunchPdf,
  punchFilePath,
  setPunchItemStatus,
  uploadPunchPhoto,
  type PunchPhotoItem,
  type PunchStatus,
} from "@/lib/punchPhotos";
import { useFeature } from "@/lib/useFeature";
import type { Locale } from "@/lib/types";

const primaryBtn =
  "inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper disabled:opacity-50";

function statusText(status: PunchStatus, m: ReturnType<typeof t>) {
  if (status === "fixed") return m.punchPhotoFixed;
  if (status === "accepted") return m.punchPhotoAccepted;
  if (status === "returned") return m.punchPhotoReturned;
  return m.punchPhotoOpen;
}

function messageFor(error: unknown, m: ReturnType<typeof t>) {
  if (error instanceof ApiError && error.status === 409) return m.punchPhotoConflict;
  if (error instanceof ApiError && error.status === 403) return m.punchPhotoForbidden;
  if (error instanceof ApiError && error.status === 404) return m.punchPhotoSaveError;
  return m.punchPhotoSaveError;
}

export function PunchPhotos({ locale, projectId }: { locale: Locale; projectId: string }) {
  const enabled = useFeature("punch_photos");
  const m = t(locale);
  const { user } = useAuth();
  const [items, setItems] = useState<PunchPhotoItem[]>([]);
  const [mine, setMine] = useState(false);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!enabled) return;
    fetchPunchItems(projectId, { mine })
      .then(setItems)
      .catch((err: unknown) => setError(messageFor(err, m)));
  }, [enabled, projectId, mine, m]);

  useEffect(() => {
    load();
  }, [load]);

  if (!enabled) return null;

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      setError(m.punchPhotoNeedTitle);
      return;
    }
    if (!photo) {
      setError(m.punchPhotoNeedPhoto);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await createPunchItem(projectId, {
        id: crypto.randomUUID(),
        title: title.trim(),
        due_date: due || undefined,
      });
      const withPhoto = await uploadPunchPhoto(projectId, created.id, photo, {
        id: crypto.randomUUID(),
        file_id: crypto.randomUUID(),
        phase: "before",
        row_version: created.row_version,
      });
      setItems((prev) => [withPhoto, ...prev.filter((item) => item.id !== withPhoto.id)]);
      setTitle("");
      setDue("");
      setPhoto(null);
    } catch (err) {
      setError(messageFor(err, m));
    } finally {
      setBusy(false);
    }
  }

  async function markFixed(item: PunchPhotoItem, file: File) {
    setBusy(true);
    setError("");
    try {
      const uploaded = await uploadPunchPhoto(projectId, item.id, file, {
        id: crypto.randomUUID(),
        file_id: crypto.randomUUID(),
        phase: "after",
        row_version: item.row_version,
      });
      const next = await setPunchItemStatus(projectId, item.id, "fixed", uploaded.row_version);
      setItems((prev) => prev.map((row) => (row.id === next.id ? next : row)));
    } catch (err) {
      setError(messageFor(err, m));
      load();
    } finally {
      setBusy(false);
    }
  }

  async function move(item: PunchPhotoItem, status: "accepted" | "returned") {
    setBusy(true);
    setError("");
    try {
      const next = await setPunchItemStatus(projectId, item.id, status, item.row_version);
      setItems((prev) => prev.map((row) => (row.id === next.id ? next : row)));
    } catch (err) {
      setError(messageFor(err, m));
      load();
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    try {
      const blob = await fetchPunchPdf(projectId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "punches.pdf";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(messageFor(err, m));
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button type="button" className={!mine ? primaryBtn : "min-h-12 rounded-full px-4 text-sm"} onClick={() => setMine(false)}>
          {m.punchPhotoAll}
        </button>
        <button type="button" className={mine ? primaryBtn : "min-h-12 rounded-full px-4 text-sm"} onClick={() => setMine(true)} disabled={!user}>
          {m.punchPhotoMine}
        </button>
        <button type="button" className="min-h-12 rounded-full px-4 text-sm underline" onClick={() => void downloadPdf()}>
          {m.punchPhotoPdf}
        </button>
      </div>
      {error ? (
        <p className="text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
      {user ? (
        <form className="grid gap-2" onSubmit={(event) => void onCreate(event)}>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={m.punchPhotoTitlePh}
            aria-label={m.punchPhotoTitlePh}
            className="min-h-12 border border-ink/15 px-2 text-sm"
          />
          <label className={`${primaryBtn} cursor-pointer`}>
            {photo ? m.punchPhotoSelected : m.punchPhotoBefore}
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
            />
          </label>
          <details>
            <summary className="min-h-12 cursor-pointer text-sm">{m.punchPhotoDue}</summary>
            <input type="date" value={due} onChange={(event) => setDue(event.target.value)} aria-label={m.punchPhotoDue} className="min-h-12 w-full border border-ink/15 px-2 text-sm" />
          </details>
          <button className={primaryBtn} disabled={busy} type="submit">
            {m.punchPhotoAdd}
          </button>
        </form>
      ) : null}
      {items.length === 0 ? <p className="text-sm text-ink/70">{m.punchPhotoEmpty}</p> : null}
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.id} className={`border border-ink/10 p-3 ${item.overdue ? "text-red-700" : ""}`}>
            <p className="font-medium">
              {item.title} · {statusText(item.status, m)}
              {item.due_date ? ` · ${item.due_date}` : ""}
            </p>
            {item.location ? <p className="text-sm">{item.location}</p> : null}
            <div className="mt-2 flex gap-2">
              {item.photos_before.map((fileId) => (
                <AuthImage key={fileId} src={punchFilePath(projectId, item.id, fileId)} alt={m.punchPhotoBefore} className="h-16 w-16 object-cover" />
              ))}
              {item.photos_after.map((fileId) => (
                <AuthImage key={fileId} src={punchFilePath(projectId, item.id, fileId)} alt={m.punchPhotoAfter} className="h-16 w-16 object-cover" />
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {user && item.can_fix ? (
                <label className="min-h-12 cursor-pointer rounded-full px-3 text-sm underline">
                  {m.punchPhotoMarkFixed}
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void markFixed(item, file);
                    }}
                  />
                </label>
              ) : null}
              {user && item.can_accept ? (
                <>
                  <button type="button" className="min-h-12 underline text-sm" onClick={() => void move(item, "accepted")}>
                    {m.punchPhotoAccept}
                  </button>
                  <button type="button" className="min-h-12 underline text-sm" onClick={() => void move(item, "returned")}>
                    {m.punchPhotoReturn}
                  </button>
                </>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
