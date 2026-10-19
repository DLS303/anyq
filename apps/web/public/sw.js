const CACHE = "anyq-static-v1";
const PRECACHE = ["/favicon.svg", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png"];

function isPrivate(url, request) {
  if (request.method !== "GET") return true;
  if (request.headers.get("authorization")) return true;
  const path = url.pathname;
  return path.startsWith("/v1/") || path.startsWith("/uploads/") || path === "/health" || path.startsWith("/api/");
}

function isCacheable(pathname) {
  return (
    pathname.startsWith("/_next/static/") ||
    pathname.startsWith("/icons/") ||
    pathname === "/favicon.svg" ||
    pathname === "/manifest.webmanifest"
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isPrivate(url, request)) return;
  if (!isCacheable(url.pathname)) return;
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(request);
      const fresh = fetch(request)
        .then((response) => {
          if (response.ok) cache.put(request, response.clone());
          return response;
        })
        .catch(() => cached);
      return cached || fresh;
    }),
  );
});
