/**
 * Which API reads the service worker keeps for offline use (NetworkFirst).
 *
 * Shared by the service worker (src/sw.ts) and the page, so keep this module
 * free of DOM and app imports.
 */

export const API_CACHE_NAME = "api-event-data";

const UUID = "[0-9a-fA-F-]{8,36}";

// Everything the scoring pages need to render after one online visit.
const CACHEABLE_API_PATHS: readonly RegExp[] = [
  /^\/api\/auth\/me$/,
  /^\/api\/v1\/events$/,
  new RegExp(`^/api/v1/events/${UUID}$`),
  new RegExp(`^/api/v1/events/${UUID}/(modules|registrations|schedule|scoring-schema|ranking|matches|phases)$`),
  /^\/api\/seasons\/active$/,
  /^\/api\/teams(\/mine)?$/,
  new RegExp(`^/api/scoring/seasons/${UUID}/(schema|matches)$`),
];

export function isOfflineCacheableApiRequest(method: string, pathname: string): boolean {
  return method === "GET" && CACHEABLE_API_PATHS.some((pattern) => pattern.test(pathname));
}

/** Drop cached API responses, e.g. on logout so the next user cannot read them offline. */
export async function clearApiCache(): Promise<void> {
  try {
    if (typeof caches !== "undefined") await caches.delete(API_CACHE_NAME);
  } catch {
    // Cache storage unavailable (private mode, tests) — nothing to clear.
  }
}
