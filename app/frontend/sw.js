// Service worker: cache-first ENDAST för versionsstämplade statiska filer
// (?v=<innehålls-hash>, stämplas i Docker-bygget). URL:en byter när innehållet
// byter, så cache-first är riskfritt — gammal JS/CSS kan aldrig serveras mot
// nytt API. Allt annat (HTML, /api/, ostämplade filer) rörs inte och går som
// vanligt över nätet med sina Cache-Control/ETag-regler.
"use strict";

const STATIC_CACHE = "flow-static-v1";
const VERSIONED_ASSET_RE = /\.(?:js|css|svg|png|ico|woff2?)$/;

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.filter((name) => name !== STATIC_CACHE).map((name) => caches.delete(name))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  if (!url.searchParams.get("v") || !VERSIONED_ASSET_RE.test(url.pathname)) return;

  event.respondWith(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      const hit = await cache.match(request);
      if (hit) return hit;
      const response = await fetch(request);
      if (response.ok) {
        await cache.put(request, response.clone());
      }
      return response;
    })()
  );
});
