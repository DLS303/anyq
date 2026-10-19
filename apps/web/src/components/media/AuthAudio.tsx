"use client";

import { useEffect, useState } from "react";

export function AuthAudio({ src, label }: { src: string; label: string }) {
  const [url, setUrl] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("superapp_token");
    const controller = new AbortController();
    let objectUrl = "";
    fetch(src, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.blob() : Promise.reject(new Error("file"))))
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!controller.signal.aborted) setUrl("");
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  if (!url) return null;
  return <audio controls src={url} className="mt-2 w-full" aria-label={label} />;
}
