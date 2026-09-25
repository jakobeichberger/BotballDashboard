/**
 * Access-token refresh shared by every caller and every tab.
 *
 * - Single flight: concurrent 401s, the session restore on app start and the
 *   profile page share one POST /auth/refresh.
 * - Across tabs: the refresh cookie is rotated on every refresh, so two tabs
 *   refreshing at once would revoke each other. A Web Lock serialises the
 *   refresh and a BroadcastChannel hands the new access token (and a logout)
 *   to the other tabs.
 * - Only a 401/403 from /auth/refresh ends the session. Rate limits (429),
 *   server errors and network failures are retried with backoff (honouring
 *   Retry-After) and then reported as "unavailable" — the user stays signed in.
 */
import axios, { type AxiosError } from "axios";
import { useAuthStore } from "@/store/authStore";
import { backoffDelay } from "@/lib/backoff";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";
const CHANNEL_NAME = "botball-auth";
const LOCK_NAME = "botball-auth-refresh";

/** Attempts per refresh for retryable failures (429, 5xx, network). */
export const REFRESH_ATTEMPTS = 3;
const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 10_000;

export type RefreshOutcome =
  | { status: "ok"; token: string }
  | { status: "unauthorized" }
  | { status: "unavailable"; error: unknown };

type AuthMessage = { type: "token"; token: string } | { type: "logout" };

let channel: BroadcastChannel | null = null;
/** Bumped whenever a new token arrives from another tab. */
let tokenVersion = 0;
let inflight: Promise<RefreshOutcome> | null = null;

function authChannel(): BroadcastChannel | null {
  if (channel || typeof BroadcastChannel === "undefined") return channel;
  try {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (event: MessageEvent<AuthMessage>) => {
      const message = event.data;
      if (message?.type === "token" && typeof message.token === "string") {
        tokenVersion += 1;
        useAuthStore.getState().setAccessToken(message.token);
      } else if (message?.type === "logout") {
        if (useAuthStore.getState().accessToken || useAuthStore.getState().user) useAuthStore.getState().logout();
      }
    };
  } catch {
    channel = null;
  }
  return channel;
}

/** Start listening for tokens and logouts of other tabs (idempotent). */
export function listenForSessionChanges(): void {
  authChannel();
}

function broadcast(message: AuthMessage): void {
  try {
    authChannel()?.postMessage(message);
  } catch {
    // Closed channel (tab shutting down) — the other tabs refresh themselves.
  }
}

/** Tell the other tabs that this user signed out. */
export function broadcastLogout(): void {
  broadcast({ type: "logout" });
}

/** Tell the other tabs about a new access token (e.g. after the login). */
export function broadcastToken(token: string): void {
  broadcast({ type: "token", token });
}

/** Milliseconds from a Retry-After header (seconds or HTTP date), if any. */
export function retryAfterMs(value: unknown, now = Date.now()): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(String(value));
  return Number.isNaN(date) ? null : Math.max(0, date - now);
}

export { backoffDelay };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function isRetryable(error: AxiosError): boolean {
  const status = error.response?.status;
  return status === undefined || status === 408 || status === 429 || status >= 500;
}

async function postRefresh(): Promise<RefreshOutcome> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < REFRESH_ATTEMPTS; attempt += 1) {
    try {
      const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {}, { withCredentials: true, timeout: 15_000 });
      if (typeof data?.access_token !== "string") return { status: "unavailable", error: new Error("no access token") };
      return { status: "ok", token: data.access_token };
    } catch (caught) {
      const error = caught as AxiosError;
      const status = error.response?.status;
      if (status === 401 || status === 403) return { status: "unauthorized" };
      lastError = error;
      if (!isRetryable(error) || attempt === REFRESH_ATTEMPTS - 1) break;
      // Offline: retrying now is pointless, the caller tries again later.
      if (typeof navigator !== "undefined" && !navigator.onLine) break;
      const wait = retryAfterMs(error.response?.headers?.["retry-after"]) ?? backoffDelay(attempt, BASE_DELAY_MS, MAX_DELAY_MS);
      await sleep(Math.min(wait, MAX_DELAY_MS * 3));
    }
  }
  return { status: "unavailable", error: lastError };
}

// ── Logout without a connection ──────────────────────────────────────────────

/** Set when the user signed out offline: the refresh cookie is still valid. */
const PENDING_LOGOUT_KEY = "botball-pending-logout";

function pendingLogout(): boolean {
  try {
    return localStorage.getItem(PENDING_LOGOUT_KEY) === "1";
  } catch {
    return false;
  }
}

/** Remember to revoke the refresh cookie once the server is reachable again. */
export function markPendingLogout(): void {
  try {
    localStorage.setItem(PENDING_LOGOUT_KEY, "1");
  } catch {
    // Storage disabled: the cookie expires on its own.
  }
}

/** A new login replaced the cookie of the offline logout. */
export function clearPendingLogout(): void {
  try {
    localStorage.removeItem(PENDING_LOGOUT_KEY);
  } catch {
    // Storage disabled — nothing was stored either.
  }
}

/** Revoke the refresh cookie of an offline logout; true when done (or nothing to do). */
export async function flushPendingLogout(): Promise<boolean> {
  if (!pendingLogout()) return true;
  try {
    await axios.post(`${BASE_URL}/auth/logout`, {}, { withCredentials: true, timeout: 15_000 });
    localStorage.removeItem(PENDING_LOGOUT_KEY);
    return true;
  } catch {
    return false;
  }
}

if (typeof window !== "undefined") window.addEventListener("online", () => void flushPendingLogout());

async function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? (navigator as Navigator & { locks?: LockManager }).locks : undefined;
  if (!locks?.request) return task();
  return locks.request(LOCK_NAME, task) as Promise<T>;
}

/**
 * Get a new access token. Concurrent callers share one request; a token another
 * tab fetched while this one waited for the lock is used as it is.
 */
export function refreshSession(): Promise<RefreshOutcome> {
  authChannel();
  if (inflight) return inflight;
  const versionAtStart = tokenVersion;
  inflight = withRefreshLock(async () => {
    // Signed out while offline: the cookie must not bring the session back.
    if (pendingLogout()) {
      await flushPendingLogout();
      return { status: "unauthorized" } as RefreshOutcome;
    }
    const shared = useAuthStore.getState().accessToken;
    if (tokenVersion !== versionAtStart && shared) return { status: "ok", token: shared } as RefreshOutcome;
    const outcome = await postRefresh();
    if (outcome.status === "ok") {
      useAuthStore.getState().setAccessToken(outcome.token);
      broadcast({ type: "token", token: outcome.token });
    }
    return outcome;
  }).finally(() => {
    inflight = null;
  });
  return inflight;
}

/** Test helper: forget the in-flight refresh and the channel. */
export function resetSessionRefresh(): void {
  inflight = null;
  tokenVersion = 0;
  channel?.close();
  channel = null;
}
