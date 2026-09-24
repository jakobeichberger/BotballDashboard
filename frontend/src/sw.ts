/// <reference lib="webworker" />
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { NetworkFirst } from "workbox-strategies";
import { ExpirationPlugin } from "workbox-expiration";
import { API_CACHE_NAME, isOfflineCacheableApiRequest } from "./lib/offlineCache";

declare const self: ServiceWorkerGlobalScope;

cleanupOutdatedCaches();

// workbox-build injects the precache manifest here at build time
precacheAndRoute(self.__WB_MANIFEST);

// SPA: serve the precached shell for every navigation so the app starts offline.
registerRoute(new NavigationRoute(createHandlerBoundToURL("/index.html"), { denylist: [/^\/api\//] }));

// The data the scoring form needs (event, teams, schedule, schema, …): always
// try the network first, fall back to the last copy when offline. Scores
// entered meanwhile are queued in IndexedDB by the page (lib/offlineQueue).
registerRoute(
  ({ url, request }) => url.origin === self.location.origin && isOfflineCacheableApiRequest(request.method, url.pathname),
  new NetworkFirst({
    cacheName: API_CACHE_NAME,
    networkTimeoutSeconds: 4,
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 24 * 60 * 60 })],
  }),
);

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("push", (event) => {
  let data: { title?: string; body?: string; url?: string } = {};
  try {
    data = event.data?.json() ?? {};
  } catch {
    data = { body: event.data?.text() };
  }
  event.waitUntil(
    self.registration.showNotification(data.title ?? "BotballDashboard", {
      body: data.body ?? "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url: data.url ?? "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url ?? "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const existing = clients.find((client) => client.url === target);
      if (existing && "focus" in existing) return existing.focus();
      return self.clients.openWindow(target);
    })
  );
});
