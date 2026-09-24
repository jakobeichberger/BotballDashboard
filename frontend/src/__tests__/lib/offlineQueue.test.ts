import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  discardQueuedScore,
  enqueueScore,
  isQueueableScoreRequest,
  listQueuedScores,
  resetQueueStore,
  retryQueuedScore,
  syncQueuedScores,
  type SyncClient,
} from "@/lib/offlineQueue";

const EVENT = "11111111-2222-3333-4444-555555555555";
const URL_EVENT = `/v1/events/${EVENT}/matches`;

function httpError(status: number, detail = "nope") {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } });
}

function client(overrides: Partial<{ get: SyncClient["get"]; post: SyncClient["post"] }> = {}): SyncClient & { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> } {
  return {
    get: vi.fn(overrides.get ?? (async () => ({ data: [] }))),
    post: vi.fn(overrides.post ?? (async () => ({ data: { id: "m1" } }))),
  } as never;
}

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

beforeEach(() => {
  // A fresh database per test.
  globalThis.indexedDB = new IDBFactory();
  resetQueueStore();
  setOnline(true);
});

afterEach(() => setOnline(true));

describe("offline score queue", () => {
  it("recognises only score-entry POSTs as queueable", () => {
    expect(isQueueableScoreRequest("post", URL_EVENT)).toBe(true);
    expect(isQueueableScoreRequest("POST", "/api/scoring/seasons/s1/matches")).toBe(true);
    expect(isQueueableScoreRequest("PATCH", "/scoring/matches/m1")).toBe(false);
    expect(isQueueableScoreRequest("POST", "/papers")).toBe(false);
    expect(isQueueableScoreRequest("GET", URL_EVENT)).toBe(false);
  });

  it("stores entries in IndexedDB keyed by their idempotency key", async () => {
    const entry = await enqueueScore(URL_EVENT, { team_id: "t1", raw_scores: { a: 1 }, idempotency_key: "key-12345678" }, "Team 1 · 10 P.", "u1");
    expect(entry).toMatchObject({ id: "key-12345678", eventId: EVENT, status: "pending", userId: "u1" });
    // A double tap re-queues the same key: still one entry.
    await enqueueScore(URL_EVENT, { team_id: "t1", idempotency_key: "key-12345678" });
    const stored = await listQueuedScores();
    expect(stored).toHaveLength(1);
    expect(stored[0].body).toMatchObject({ team_id: "t1", idempotency_key: "key-12345678" });
  });

  it("adds an idempotency key when the body has none", async () => {
    const entry = await enqueueScore("/scoring/seasons/s1/matches", { team_id: "t1" });
    expect(typeof entry.body.idempotency_key).toBe("string");
    expect(entry.id).toBe(entry.body.idempotency_key);
  });

  it("syncs pending entries and removes them on success", async () => {
    await enqueueScore(URL_EVENT, { team_id: "t1", idempotency_key: "key-aaaaaaaa" });
    const api = client();
    const result = await syncQueuedScores(api, "u1");
    expect(result).toEqual({ synced: 1, failed: 0, remaining: 0 });
    expect(api.post).toHaveBeenCalledWith(URL_EVENT, expect.objectContaining({ idempotency_key: "key-aaaaaaaa" }), { _fromOfflineQueue: true });
    expect(await listQueuedScores()).toEqual([]);
  });

  it("marks 409 as conflict and other 4xx as error, keeping them for the user", async () => {
    await enqueueScore(URL_EVENT, { team_id: "t1", idempotency_key: "key-conflict" });
    await enqueueScore(URL_EVENT, { team_id: "t2", idempotency_key: "key-invalid1" });
    const api = client({
      post: async (_url, body) => {
        throw (body as { team_id: string }).team_id === "t1" ? httpError(409, "Idempotency key is already used") : httpError(422, "Unknown score field");
      },
    });
    const result = await syncQueuedScores(api, "u1");
    expect(result).toEqual({ synced: 0, failed: 2, remaining: 2 });
    const byId = Object.fromEntries((await listQueuedScores()).map((entry) => [entry.id, entry]));
    expect(byId["key-conflict"]).toMatchObject({ status: "conflict", error: "Idempotency key is already used" });
    expect(byId["key-invalid1"]).toMatchObject({ status: "error", error: "Unknown score field" });

    // Failed entries are not retried automatically …
    await syncQueuedScores(api, "u1");
    expect(api.post).toHaveBeenCalledTimes(2);
    // … only after an explicit retry; discard drops them.
    await retryQueuedScore("key-invalid1");
    expect((await listQueuedScores()).find((entry) => entry.id === "key-invalid1")?.status).toBe("pending");
    await discardQueuedScore("key-conflict");
    expect((await listQueuedScores()).map((entry) => entry.id)).toEqual(["key-invalid1"]);
  });

  it("keeps entries pending on network errors and server errors", async () => {
    await enqueueScore(URL_EVENT, { team_id: "t1", idempotency_key: "key-network" });
    const api = client({ post: async () => { throw new Error("Network Error"); } });
    const result = await syncQueuedScores(api, "u1");
    expect(result.synced).toBe(0);
    const [entry] = await listQueuedScores();
    expect(entry).toMatchObject({ status: "pending", attempts: 1, error: "Network Error" });
  });

  it("does not sync while offline", async () => {
    await enqueueScore(URL_EVENT, { team_id: "t1", idempotency_key: "key-offline1" });
    setOnline(false);
    const api = client();
    await syncQueuedScores(api, "u1");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("detects a score entered meanwhile for the same team and match", async () => {
    await enqueueScore(URL_EVENT, { team_id: "t1", scheduled_match_id: "sm1", idempotency_key: "key-mine0001" });
    const api = client({
      get: async () => ({ data: [{ id: "other", team_id: "t1", scheduled_match_id: "sm1", idempotency_key: "someone-else" }] }),
    });
    const result = await syncQueuedScores(api, "u1");
    expect(result.failed).toBe(1);
    expect(api.get).toHaveBeenCalledWith(`/v1/events/${EVENT}/matches`, { params: { team_id: "t1" } });
    expect(api.post).not.toHaveBeenCalled();
    const [entry] = await listQueuedScores();
    expect(entry.status).toBe("conflict");

    // "Save anyway" skips the check.
    await retryQueuedScore(entry.id, true);
    await syncQueuedScores(api, "u1");
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(await listQueuedScores()).toEqual([]);
  });

  it("treats its own already-synced entry as no conflict", async () => {
    await enqueueScore(URL_EVENT, { team_id: "t1", scheduled_match_id: "sm1", idempotency_key: "key-mine0002" });
    const api = client({
      get: async () => ({ data: [{ id: "m1", team_id: "t1", scheduled_match_id: "sm1", idempotency_key: "key-mine0002" }] }),
    });
    expect((await syncQueuedScores(api, "u1")).synced).toBe(1);
  });

  it("only replays entries of the signed-in user", async () => {
    await enqueueScore(URL_EVENT, { team_id: "t1", idempotency_key: "key-user-a01" }, "", "a");
    await enqueueScore(URL_EVENT, { team_id: "t2", idempotency_key: "key-user-b01" }, "", "b");
    const api = client();
    const result = await syncQueuedScores(api, "a");
    expect(result).toEqual({ synced: 1, failed: 0, remaining: 1 });
    expect((await listQueuedScores())[0].userId).toBe("b");
  });
});
