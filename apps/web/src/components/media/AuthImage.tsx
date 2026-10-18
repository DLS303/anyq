"use client";

import { useEffect, useState } from "react";

function needsSession(src: string) {
  return src.startsWith("/v1/files/") || src.startsWith("/uploads/");
}

export function AuthImage({ src, alt = "", className }: { src: string; alt?: string; className?: string }) {
  const [url, setUrl] = useState(needsSession(src) ? "" : src);

  useEffect(() => {
    if (!needsSession(src)) {
      setUrl(src);
      return;
    }
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

  if (!url) return <div className={className} />;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={url} alt={alt} className={className} />
  );
}
