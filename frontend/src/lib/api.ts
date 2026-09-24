import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/authStore";
import { enqueueScore, isQueueableScoreRequest, newIdempotencyKey } from "@/lib/offlineQueue";

declare module "axios" {
  interface AxiosRequestConfig {
    /** Replayed from the offline queue — never queue it again. */
    _fromOfflineQueue?: boolean;
    /** Summary shown in the pending-sync list if the request gets queued. */
    offlineLabel?: string;
  }
}

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

export async function restoreAccessToken(): Promise<string | null> {
  try {
    const { data } = await axios.post(
      `${BASE_URL}/auth/refresh`,
      {},
      { withCredentials: true }
    );
    return data.access_token;
  } catch {
    return null;
  }
}

export const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
});

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
  if (method && !["GET", "HEAD", "OPTIONS"].includes(method) && !navigator.onLine) {
    // Score entries are stored locally and synced later; every other write
    // needs a connection.
    if (queueable) {
      config.adapter = () => queueRequest(config);
      return config;
    }
    return Promise.reject(new Error("OFFLINE_WRITE_BLOCKED"));
  }
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auto-refresh on 401
let isRefreshing = false;
let queue: Array<(token: string | null) => void> = [];

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.data?.message && !error.response.data.detail) {
      error.response.data.detail = error.response.data.message;
    }
    const original = error.config;
    // The connection dropped mid-request: keep the score entry for later.
    if (!error.response && !axios.isCancel(error) && original && !original._fromOfflineQueue && isQueueableScoreRequest(original.method, original.url)) {
      return queueRequest(original);
    }
    if (
      error.response?.status === 401 &&
      !original._retry &&
      !String(original.url).includes("/auth/refresh")
    ) {
      original._retry = true;
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          queue.push((token) => {
            if (!token) {
              reject(error);
              return;
            }
            original.headers.Authorization = `Bearer ${token}`;
            resolve(api(original));
          });
        });
      }
      isRefreshing = true;
      try {
        const { data } = await axios.post(
          `${BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true }
        );
        useAuthStore.getState().setAccessToken(data.access_token);
        queue.forEach((cb) => cb(data.access_token));
        queue = [];
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch {
        // Notify queued requests that refresh failed
        queue.forEach((cb) => cb(""));
        queue = [];
        useAuthStore.getState().logout();
        window.location.href = "/login";
        return Promise.reject(error);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);
