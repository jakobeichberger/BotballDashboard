/**
 * Offline queue for score entries (spec 09 "Offline-Modus").
 *
 * Score POSTs made without a connection are stored in IndexedDB under their
 * idempotency key and replayed when the browser is back online (and on app
 * start). The backend treats a repeated idempotency key as the same entry, so
 * a replay after a lost response never creates a duplicate.
 *
 * Only new score entries are queued; every other write stays blocked offline
 * (see the request interceptor in lib/api.ts).
 */
import { createStore, del, entries, get, set, type UseStore } from "idb-keyval";
import i18n from "@/i18n/config";
import { apiErrorMessage } from "@/lib/errors";

export type QueuedScoreStatus = "pending" | "syncing" | "conflict" | "error";

export interface QueuedScore {
  /** = idempotency_key of the request body */
  id: string;
  /** API path relative to the axios baseURL, e.g. /v1/events/{id}/matches */
  url: string;
  body: Record<string, unknown>;
  eventId: string | null;
  /**
   * Who entered it; only that user's session replays it. null (no profile was
   * known yet) is never replayed automatically: a signed-in user has to claim
   * the entry first (claimQueuedScore).
   */
  userId: string | null;
  /** Human-readable summary for the pending list (team, match, total). */
  label: string;
  createdAt: string;
  status: QueuedScoreStatus;
  attempts: number;
  error?: string;
  /** Skip the duplicate check on the next sync (user chose "save anyway"). */
  force?: boolean;
}

export interface ScoreRequestMeta {
  offlineLabel?: string;
}

// POST endpoints that create a score entry and may be queued offline.
const QUEUEABLE = [
  /^\/v1\/events\/([^/]+)\/matches$/,
  /^\/scoring\/seasons\/[^/]+\/matches$/,
];

export const QUEUE_CHANGED_EVENT = "botball:offline-queue-changed";

let store: UseStore | null = null;
function queueStore(): UseStore {
  store ??= createStore("botball-offline", "score-queue");
  return store;
}

/** For tests: forget the store so a fresh IndexedDB is picked up. */
export function resetQueueStore(): void {
  store = null;
}

function notify(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(QUEUE_CHANGED_EVENT));
}

function normalizePath(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "").replace(/^\/api(?=\/)/, "").split("?")[0];
}

export function isQueueableScoreRequest(method: string | undefined, url: string | undefined): boolean {
  if (!url || method?.toUpperCase() !== "POST") return false;
  const path = normalizePath(url);
  return QUEUEABLE.some((pattern) => pattern.test(path));
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `offline-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export async function enqueueScore(
  url: string,
  body: Record<string, unknown>,
  label = "",
  userId: string | null = null,
): Promise<QueuedScore> {
  const id = typeof body.idempotency_key === "string" ? body.idempotency_key : newIdempotencyKey();
  const path = normalizePath(url);
  const entry: QueuedScore = {
    id,
    url: path,
    body: { ...body, idempotency_key: id },
    eventId: path.match(QUEUEABLE[0])?.[1] ?? (typeof body.event_id === "string" ? body.event_id : null),
    userId,
    label,
    createdAt: new Date().toISOString(),
    status: "pending",
    attempts: 0,
  };
  // Re-queueing the same key (double tap) keeps the original entry.
  const existing = await get<QueuedScore>(id, queueStore());
  if (existing) return existing;
  await set(id, entry, queueStore());
  notify();
  return entry;
}

export async function listQueuedScores(): Promise<QueuedScore[]> {
  const all = await entries<string, QueuedScore>(queueStore());
  return all.map(([, value]) => value).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function updateQueuedScore(id: string, patch: Partial<QueuedScore>): Promise<void> {
  const existing = await get<QueuedScore>(id, queueStore());
  if (!existing) return;
  await set(id, { ...existing, ...patch }, queueStore());
  notify();
}

export async function discardQueuedScore(id: string): Promise<void> {
  await del(id, queueStore());
  notify();
}

/** Take over an entry recorded without a known user, so this user's session sends it. */
export async function claimQueuedScore(id: string, userId: string): Promise<void> {
  await updateQueuedScore(id, { userId, status: "pending", error: undefined });
}

/** Mark an entry for another attempt; `force` skips the duplicate check. */
export async function retryQueuedScore(id: string, force = false): Promise<void> {
  await updateQueuedScore(id, { status: "pending", error: undefined, force });
}

// ── Sync ─────────────────────────────────────────────────────────────────────

interface HttpError {
  response?: { status: number; data?: { detail?: unknown } };
  message?: string;
  code?: string;
}

export interface SyncClient {
  get(url: string, config?: { params?: Record<string, unknown> }): Promise<{ data: unknown }>;
  post(url: string, body: unknown, config?: { _fromOfflineQueue?: boolean }): Promise<{ data: unknown }>;
}

export interface SyncResult {
  synced: number;
  failed: number;
  remaining: number;
}

/** The reason shown next to the entry, in the UI language (lib/errors). */
function detailOf(error: HttpError): string {
  return apiErrorMessage(error, i18n.t("printing:cancel.unknownError"));
}

interface ExistingMatch {
  id: string;
  team_id: string;
  scheduled_match_id: string | null;
  idempotency_key?: string | null;
}

/**
 * Conflict check for an entry bound to a scheduled match: did someone else
 * score this team in this match while we were offline?
 */
async function findConflict(client: SyncClient, entry: QueuedScore): Promise<ExistingMatch | null> {
  const scheduledMatchId = entry.body.scheduled_match_id;
  if (!entry.eventId || typeof scheduledMatchId !== "string" || !scheduledMatchId) return null;
  const { data } = await client.get(`/v1/events/${entry.eventId}/matches`, { params: { team_id: entry.body.team_id } });
  const matches = Array.isArray(data) ? (data as ExistingMatch[]) : [];
  return matches.find((match) => match.scheduled_match_id === scheduledMatchId && match.idempotency_key !== entry.id) ?? null;
}

let running: Promise<SyncResult> | null = null;

/**
 * Entries shown to this user: their own, plus those recorded without a known
 * user (which they may claim or discard). Nothing before the user is known.
 */
export function belongsTo(entry: QueuedScore, userId: string | null | undefined): boolean {
  return !!userId && (entry.userId === userId || !entry.userId);
}

/** Entries recorded without a known user wait to be claimed. */
export function isUnclaimed(entry: QueuedScore): boolean {
  return !entry.userId;
}

/**
 * Replay every pending entry of this user. Network failures and 5xx keep the
 * entry pending for the next attempt; 409 marks it as a conflict and other
 * 4xx as an error, both waiting for the user to retry or discard it.
 */
export function syncQueuedScores(client: SyncClient, userId?: string | null): Promise<SyncResult> {
  running ??= (async () => {
    let synced = 0;
    let failed = 0;
    try {
      for (const entry of await listQueuedScores()) {
        // "syncing" left over from a closed tab counts as pending.
        if (entry.status !== "pending" && entry.status !== "syncing") continue;
        // Strictly the author's session: another user must never submit it.
        if (!userId || entry.userId !== userId) continue;
        if (typeof navigator !== "undefined" && !navigator.onLine) break;
        await updateQueuedScore(entry.id, { status: "syncing", attempts: entry.attempts + 1 });
        try {
          if (!entry.force) {
            const conflict = await findConflict(client, entry);
            if (conflict) {
              await updateQueuedScore(entry.id, {
                status: "conflict",
                error: i18n.t("common:pendingScores.conflictExisting"),
              });
              failed += 1;
              continue;
            }
          }
          await client.post(entry.url, entry.body, { _fromOfflineQueue: true });
          await discardQueuedScore(entry.id);
          synced += 1;
        } catch (caught) {
          const error = caught as HttpError;
          const status = error.response?.status;
          if (status === undefined || status >= 500) {
            // Offline again or server trouble — try again later.
            await updateQueuedScore(entry.id, { status: "pending", error: detailOf(error) });
            break;
          }
          await updateQueuedScore(entry.id, { status: status === 409 ? "conflict" : "error", error: detailOf(error) });
          failed += 1;
        }
      }
      const remaining = (await listQueuedScores()).length;
      return { synced, failed, remaining };
    } finally {
      running = null;
    }
  })();
  return running;
}
