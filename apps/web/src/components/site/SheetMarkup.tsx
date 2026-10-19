"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";
import { t } from "@/i18n/messages";
import { apiFetch, fetchAuthorizedBlob } from "@/lib/api";
import { preparePhoto } from "@/lib/photos";
import {
  MARKUP_TOOLS,
  arrowShape,
  beginTool,
  cloudPath,
  cloudShape,
  finishPhoto,
  finishText,
  idleDraft,
  markupFilePath,
  markupPath,
  photoShape,
  placePoint,
  unitPoint,
  type Draft,
  type MarkupShape,
  type MarkupTool,
  type MarkupVisibility,
} from "@/lib/markups";
import type { Locale } from "@/lib/types";
import { PdfDrawingViewer } from "./PdfDrawingViewer";

type Markup = {
  id: string;
  revision_id: string;
  shapes: MarkupShape[];
  visibility: MarkupVisibility;
  row_version: number;
};

type ListPayload = { can_write: boolean; markups: Markup[] };

const TOOL_LABEL = {
  arrow: "markupArrow",
  cloud: "markupCloud",
  text: "markupText",
  photo: "markupPhoto",
} as const;

export function SheetMarkup({
  locale,
  revisionId,
  fileKey,
  loadFile,
}: {
  locale: Locale;
  revisionId: string;
  fileKey: string;
  loadFile: () => Promise<ArrayBuffer>;
}) {
  const m = t(locale);
  const fileRef = useRef<HTMLInputElement>(null);
  const [markups, setMarkups] = useState<Markup[]>([]);
  const [canWrite, setCanWrite] = useState<boolean | null>(null);
  const [visibility, setVisibility] = useState<MarkupVisibility>("project");
  const [draft, setDraft] = useState<Draft>(idleDraft());
  const [error, setError] = useState("");
  const [photos, setPhotos] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    if (!revisionId) return;
    const res = await apiFetch(markupPath(revisionId));
    if (res.status === 404) {
      setCanWrite(false);
      setMarkups([]);
      return;
    }
    if (!res.ok) {
      setError(m.markupError);
      return;
    }
    const body = (await res.json()) as { data: ListPayload };
    setMarkups(body.data.markups || []);
    setCanWrite(Boolean(body.data.can_write));
    setError("");
  }, [m.markupError, revisionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const urls: string[] = [];
    let alive = true;
    const ids = markups.flatMap((item) =>
      item.shapes.filter((shape) => shape.type === "photo").map((shape) => shape.file_id),
    );
    void (async () => {
      const next: Record<string, string> = {};
      for (const fileId of ids) {
        try {
          const blob = await fetchAuthorizedBlob(markupFilePath(revisionId, fileId));
          const url = URL.createObjectURL(blob);
          urls.push(url);
          next[fileId] = url;
        } catch {
          next[fileId] = "";
        }
      }
      if (alive) setPhotos(next);
    })();
    return () => {
      alive = false;
      for (const url of urls) URL.revokeObjectURL(url);
    };
  }, [markups, revisionId]);

  async function save(shapes: MarkupShape[], file?: File) {
    setError("");
    const id = crypto.randomUUID();
    let res: Response;
    if (file) {
      const body = new FormData();
      body.append("payload", JSON.stringify({ id, row_version: 0, visibility, shapes }));
      body.append("file", await preparePhoto(file));
      res = await apiFetch(markupPath(revisionId), { method: "POST", body });
    } else {
      res = await apiFetch(markupPath(revisionId), {
        method: "POST",
        body: JSON.stringify({ id, row_version: 0, visibility, shapes }),
      });
    }
    if (res.status === 409) {
      setError(m.markupConflict);
      await load();
      return;
    }
    if (!res.ok) {
      setError(res.status === 400 && file ? m.markupPhotoOnly : m.markupError);
      return;
    }
    setDraft(idleDraft());
    await load();
  }

  function onTool(tool: MarkupTool) {
    setDraft(beginTool(tool));
    setError("");
  }

  function onSheet(event: PointerEvent<SVGSVGElement>) {
    if (!draft.tool || canWrite !== true) return;
    const point = unitPoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
    const placed = placePoint(draft, point);
    setDraft(placed.draft);
    if (placed.ready === "arrow") void save([arrowShape(placed.points)]);
    if (placed.ready === "cloud") void save([cloudShape(placed.points)]);
    if (placed.ready === "photo") fileRef.current?.click();
  }

  function onText(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const note = String(new FormData(event.currentTarget).get("note") || "");
    const done = finishText(draft, note);
    if (!done.shape) return;
    void save([done.shape]);
  }

  async function onPhoto(file: File | undefined) {
    const done = finishPhoto(draft, crypto.randomUUID());
    if (!file || !done.shape) return;
    const shape = photoShape(draft.points[0], done.shape.file_id);
    await save([shape], file);
  }

  const overlay = (
    <svg
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
      className={`h-full w-full ${draft.tool ? "pointer-events-auto" : "pointer-events-none"}`}
      onPointerDown={onSheet}
    >
      {markups.flatMap((item) => item.shapes.map((shape, index) => renderShape(shape, `${item.id}-${index}`, photos, m.markupPhoto)))}
      {draft.tool === "arrow" && draft.points[0] ? (
        <circle cx={draft.points[0].x} cy={draft.points[0].y} r={0.012} className="fill-clay" />
      ) : null}
    </svg>
  );

  return (
    <div className="grid gap-2">
      <PdfDrawingViewer locale={locale} fileKey={fileKey} loadFile={loadFile} overlay={overlay} />
      {canWrite ? (
        <div className="grid gap-2" data-markup-tools>
          <div className="grid grid-cols-4 gap-1">
            {MARKUP_TOOLS.map((tool) => (
              <button
                key={tool}
                type="button"
                aria-pressed={draft.tool === tool}
                className={`min-h-12 rounded-full px-1 text-xs ${draft.tool === tool ? "bg-pine text-paper" : "border border-ink/15"}`}
                onClick={() => onTool(tool)}
              >
                {m[TOOL_LABEL[tool]]}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-1">
            <button
              type="button"
              aria-pressed={visibility === "me"}
              className={`min-h-12 rounded-full px-2 text-xs ${visibility === "me" ? "bg-ink text-paper" : "border border-ink/15"}`}
              onClick={() => setVisibility("me")}
            >
              {m.markupMine}
            </button>
            <button
              type="button"
              aria-pressed={visibility === "project"}
              className={`min-h-12 rounded-full px-2 text-xs ${visibility === "project" ? "bg-ink text-paper" : "border border-ink/15"}`}
              onClick={() => setVisibility("project")}
            >
              {m.markupShared}
            </button>
          </div>
          {draft.tool === "text" && draft.points.length === 1 ? (
            <form className="flex gap-2" onSubmit={onText}>
              <input name="note" required maxLength={200} aria-label={m.markupNote} className="min-h-12 min-w-0 flex-1 border border-ink/15 px-2 text-sm" />
              <button type="submit" className="min-h-12 rounded-full bg-pine px-3 text-sm text-paper">
                {m.markupSave}
              </button>
            </form>
          ) : null}
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              void onPhoto(file);
            }}
          />
        </div>
      ) : canWrite === false ? (
        <p className="text-xs text-ink/60">{m.markupReadOnly}</p>
      ) : null}
      {error ? <p className="text-sm text-clay">{error}</p> : null}
    </div>
  );
}

function renderShape(shape: MarkupShape, key: string, photos: Record<string, string>, photoLabel: string) {
  if (shape.type === "arrow") {
    const angle = Math.atan2(shape.y2 - shape.y1, shape.x2 - shape.x1);
    const size = 0.045;
    const tip = `${shape.x2},${shape.y2}`;
    const left = `${shape.x2 - size * Math.cos(angle - 0.45)},${shape.y2 - size * Math.sin(angle - 0.45)}`;
    const right = `${shape.x2 - size * Math.cos(angle + 0.45)},${shape.y2 - size * Math.sin(angle + 0.45)}`;
    return (
      <g key={key}>
        <line x1={shape.x1} y1={shape.y1} x2={shape.x2} y2={shape.y2} className="stroke-clay" strokeWidth={0.02} />
        <polygon points={`${tip} ${left} ${right}`} className="fill-clay" />
      </g>
    );
  }
  if (shape.type === "cloud") {
    return <path key={key} d={cloudPath(shape)} className="fill-clay/20 stroke-clay" strokeWidth={0.012} />;
  }
  if (shape.type === "text") {
    return (
      <text key={key} x={shape.x} y={shape.y} fontSize={0.04} className="fill-ink">
        {shape.text}
      </text>
    );
  }
  const href = photos[shape.file_id];
  if (!href) {
    return <rect key={key} x={shape.x} y={shape.y} width={shape.w} height={shape.h} className="fill-ink/10" />;
  }
  return <image key={key} href={href} x={shape.x} y={shape.y} width={shape.w} height={shape.h} aria-label={photoLabel} />;
}
