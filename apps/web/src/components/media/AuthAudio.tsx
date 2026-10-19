"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { t } from "@/i18n/messages";
import { fetchAuthorizedBlob, isAbortError } from "@/lib/api";

export function AuthAudio({ src, label }: { src: string; label: string }) {
  const pathname = usePathname();
  const m = t(pathname?.startsWith("/kk") ? "kk" : "ru");
  const [attempt, setAttempt] = useState(0);
  const [url, setUrl] = useState("");
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
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

  if (phase === "loading") return <p className="mt-2 text-xs text-ink/45">{m.hubLoading}</p>;
  if (phase === "error" || !url) {
    return (
      <button type="button" className="mt-2 min-h-11 text-sm text-pine" onClick={() => setAttempt((n) => n + 1)}>
        {m.retry}
      </button>
    );
  }
  return <audio controls src={url} className="mt-2 w-full max-w-full" aria-label={label} />;
}
