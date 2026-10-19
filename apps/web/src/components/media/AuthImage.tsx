"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { PhotoView } from "@/components/media/PhotoView";
import { t } from "@/i18n/messages";
import { fetchAuthorizedBlob, isAbortError } from "@/lib/api";

function needsSession(src: string) {
  return src.startsWith("/v1/files/") || src.startsWith("/uploads/");
}

export function AuthImage({ src, alt = "", className }: { src: string; alt?: string; className?: string }) {
  const pathname = usePathname();
  const m = t(pathname?.startsWith("/kk") ? "kk" : "ru");
  const [attempt, setAttempt] = useState(0);
  const [url, setUrl] = useState(needsSession(src) ? "" : src);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">(needsSession(src) ? "loading" : "ready");

  useEffect(() => {
    if (!needsSession(src)) {
      setUrl(src);
      setPhase("ready");
      return;
    }
    const controller = new AbortController();
    let objectUrl = "";
    setPhase("loading");
    fetchAuthorizedBlob(src, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        setPhase("ready");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbortError(error)) return;
        setPhase("error");
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, attempt]);

  if (phase === "loading") {
    return <div role="status" aria-busy="true" className={`animate-pulse bg-ink/10 ${className ?? ""}`} />;
  }
  if (phase === "error" || !url) {
    return (
      <button type="button" className={`min-h-12 bg-ink/5 text-xs text-pine ${className ?? ""}`} onClick={() => setAttempt((n) => n + 1)}>
        {m.retry}
      </button>
    );
  }
  return <PhotoView src={url} alt={alt} className={className} />;
}
