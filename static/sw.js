// Caches the static app shell only -- never API responses. Trip planning
// needs live data (weather, places, routes, the reasoning loop itself), so
// serving a cached plan while offline would be actively misleading rather
// than helpful. This only makes the shell (HTML/CSS/JS/icons) load fast and
// available offline; app.js is responsible for refusing to submit the form
// without a connection (see the "no connection" check there).

// Bump this whenever any file in SHELL_ASSETS changes. The `activate`
// handler below deletes every cache whose name isn't this one, so bumping
// it is what actually gets a changed shell asset in front of a returning
// user -- without it, a browser that already installed this service
// worker keeps serving what it cached under the old name indefinitely.
const CACHE_NAME = "travel-planner-shell-v3";
const SHELL_ASSETS = [
  "/",
  "/style.css",
  "/app.js",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-512-maskable.png",
];

// The app's auth middleware (main.py) returns a 401 login-page body for
// *any* unauthenticated request to *any* path, not just navigations. If
// this service worker ever (re)installs without a valid session -- e.g. a
// CACHE_NAME bump ships while a returning user's cookie has lapsed -- a
// naive cache.put() would happily cache that login-page HTML under the
// "/style.css" key forever, and cache-first means it'd then be served
// even while online, until the next CACHE_NAME bump. Only cache genuine
// 200s; let everything else fall through to a real network request.
function cacheIfOk(cache, url, response) {
  if (response.ok) {
    cache.put(url, response.clone());
  }
  return response;
}

self.addEventListener("install", (event) => {
  // Deliberately not cache.addAll(SHELL_ASSETS): its internal fetches can be
  // satisfied by the browser's ordinary HTTP cache, which would let a user
  // with a already-primed cache install this service worker against stale
  // pre-deploy assets. {cache: "reload"} forces each one to actually hit
  // the network, so the shell that gets cached is always what's live now.
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        SHELL_ASSETS.map((url) => fetch(url, { cache: "reload" }).then((response) => cacheIfOk(cache, url, response)))
      )
    )
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never intercept API calls, the SSE stream, or the login flow -- these
  // are inherently dynamic/live and must always reach the network.
  if (url.pathname.startsWith("/api/") || url.pathname === "/login") {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).catch(() => {
        if (event.request.mode === "navigate") {
          return caches.match("/");
        }
        throw new Error("Offline and this resource was never cached.");
      });
    })
  );
});
