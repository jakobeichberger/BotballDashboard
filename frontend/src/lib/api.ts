import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/authStore";
import { enqueueScore, isQueueableScoreRequest, newIdempotencyKey } from "@/lib/offlineQueue";
import { broadcastLogout, refreshSession } from "@/lib/sessionRefresh";

declare module "axios" {
  interface AxiosRequestConfig {
    /** Replayed from the offline queue — never queue it again. */
    _fromOfflineQueue?: boolean;
    /** Summary shown in the pending-sync list if the request gets queued. */
    offlineLabel?: string;
  }
}

/** Error message of a write rejected because there is no connection. */
export const OFFLINE_WRITE_BLOCKED = "OFFLINE_WRITE_BLOCKED";

/**
 * Client-side request timeout. A hung write (captive portal, dead Wi-Fi at the
 * table) fails after this, and a score entry lands in the offline queue instead
 * of leaving the button spinning.
 */
export const REQUEST_TIMEOUT_MS = 15_000;

/** Body of the 202 response a queued score request resolves with. */
export interface QueuedResponse {
  queued: true;
  idempotency_key: string;
}

export function isQueuedResponse(data: unknown): data is QueuedResponse {
  return typeof data === "object" && data !== null && (data as QueuedResponse).queued === true;
}

function bodyOf(config: InternalAxiosRequestConfig): Record<string, unknown> {
  const data = typeof config.data === "string" ? safeParse(config.data) : config.data;
  return data && typeof data === "object" && !(data instanceof FormData) ? (data as Record<string, unknown>) : {};
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function queueRequest(config: InternalAxiosRequestConfig): Promise<AxiosResponse<QueuedResponse>> {
  const userId = useAuthStore.getState().user?.id ?? null;
  const entry = await enqueueScore(config.url ?? "", bodyOf(config), config.offlineLabel ?? "", userId);
  return { data: { queued: true, idempotency_key: entry.id }, status: 202, statusText: "Queued offline", headers: {}, config };
}

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

/**
 * A fresh access token from the refresh cookie, or null. Shares the in-flight
 * refresh with the 401 handling below (lib/sessionRefresh).
 */
export async function restoreAccessToken(): Promise<string | null> {
  const outcome = await refreshSession();
  return outcome.status === "ok" ? outcome.token : null;
}

export const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
  timeout: REQUEST_TIMEOUT_MS,
});

/** No connection, or signed in read-only from the cached profile. */
function writesBlocked(): boolean {
  const { offlineSession, accessToken } = useAuthStore.getState();
  return !navigator.onLine || (offlineSession && !accessToken);
}

// Attach access token to every request
api.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase();
  const queueable = isQueueableScoreRequest(method, config.url) && !config._fromOfflineQueue;
  if (queueable) {
    // Every score entry carries an idempotency key, so a replay from the
    // offline queue can never be counted twice.
    const body = bodyOf(config);
    if (typeof body.idempotency_key !== "string") config.data = { ...body, idempotency_key: newIdempotencyKey() };
  }
  if (method && !["GET", "HEAD", "OPTIONS"].includes(method) && writesBlocked()) {
    // Score entries are stored locally and synced later; every other write
    // needs a connection.
    if (queueable) {
      config.adapter = () => queueRequest(config);
      return config;
    }
    return Promise.reject(new Error(OFFLINE_WRITE_BLOCKED));
  }
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** The refresh cookie was rejected: sign out here and in the other tabs. */
function endSession(): void {
  useAuthStore.getState().logout();
  broadcastLogout();
  if (!window.location.pathname.startsWith("/login")) window.location.assign("/login");
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.data?.message && !error.response.data.detail) {
      error.response.data.detail = error.response.data.message;
    }
    const original = error.config;
    // The connection dropped mid-request or it timed out: keep the score
    // entry for later.
    if (!error.response && !axios.isCancel(error) && original && !original._fromOfflineQueue && isQueueableScoreRequest(original.method, original.url)) {
      return queueRequest(original);
    }
    // A 401 from the login itself means wrong credentials, not an expired
    // session: refreshing (and redirecting to /login) would swallow the
    // error message the login form shows.
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !/\/auth\/(refresh|login)$/.test(String(original.url))
    ) {
      original._retry = true;
      // Another request (or tab) got a new token since this one was sent:
      // simply try again with it.
      const sent = String(original.headers?.Authorization ?? "").replace(/^Bearer /, "");
      const current = useAuthStore.getState().accessToken;
      if (current && current !== sent) {
        original.headers.Authorization = `Bearer ${current}`;
        return api(original);
      }
      const outcome = await refreshSession();
      if (outcome.status === "ok") {
        original.headers.Authorization = `Bearer ${outcome.token}`;
        return api(original);
      }
      // Only a rejected refresh cookie ends the session. A rate limit, server
      // error or lost connection keeps the user signed in; the request fails.
      if (outcome.status === "unauthorized") endSession();
      return Promise.reject(error);
    }
    return Promise.reject(error);
  }
);
