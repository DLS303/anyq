/** Requests that must never be stored by the service worker. */
export function isPrivateApiRequest(pathname: string, method = "GET", authorization: string | null = null) {
  if (method !== "GET") return true;
  if (authorization) return true;
  return (
    pathname.startsWith("/v1/") ||
    pathname.startsWith("/uploads/") ||
    pathname === "/health" ||
    pathname.startsWith("/api/")
  );
}

/** Static files the service worker may keep. HTML and API payloads are excluded. */
export function isCacheableStatic(pathname: string) {
  return (
    pathname.startsWith("/_next/static/") ||
    pathname.startsWith("/icons/") ||
    pathname === "/favicon.svg" ||
    pathname === "/manifest.webmanifest"
  );
}
