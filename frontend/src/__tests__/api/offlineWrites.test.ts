import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { api, isQueuedResponse } from "@/lib/api";
import { listQueuedScores, resetQueueStore } from "@/lib/offlineQueue";
import { useAuthStore } from "@/store/authStore";

const EVENT = "11111111-2222-3333-4444-555555555555";

describe("offline writes", () => {
  beforeEach(() => {
    globalThis.indexedDB = new IDBFactory();
    resetQueueStore();
    useAuthStore.setState({ user: { id: "juror-1" } as never });
  });

  afterEach(() => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
  });

  it("rejects a mutation before it reaches the network while offline", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    await expect(api.post("/offline-test", {})).rejects.toThrow("OFFLINE_WRITE_BLOCKED");
    await expect(api.patch("/scoring/matches/m1", { raw_scores: {} })).rejects.toThrow("OFFLINE_WRITE_BLOCKED");
  });

  it("queues a score entry instead of blocking it", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    const response = await api.post(
      `/v1/events/${EVENT}/matches`,
      { team_id: "t1", raw_scores: { a: 2 }, idempotency_key: "key-offline-1" },
      { offlineLabel: "Team 1 · 20 P." },
    );
    expect(response.status).toBe(202);
    expect(isQueuedResponse(response.data)).toBe(true);
    const [entry] = await listQueuedScores();
    expect(entry).toMatchObject({
      id: "key-offline-1",
      url: `/v1/events/${EVENT}/matches`,
      eventId: EVENT,
      userId: "juror-1",
      label: "Team 1 · 20 P.",
      status: "pending",
    });
  });

  it("queues a score entry when the connection drops mid-request", async () => {
    const response = await api.post(
      `/v1/events/${EVENT}/matches`,
      { team_id: "t1", raw_scores: {} },
      { adapter: (config) => Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config)) },
    );
    expect(response.status).toBe(202);
    const [entry] = await listQueuedScores();
    // The key was added before sending, so a lost response cannot double-count.
    expect(entry.id).toMatch(/.{8,}/);
    expect(entry.body.idempotency_key).toBe(entry.id);
  });

  it("does not queue other failed writes", async () => {
    await expect(
      api.post("/papers", {}, { adapter: (config) => Promise.reject(new AxiosError("Network Error", "ERR_NETWORK", config)) }),
    ).rejects.toThrow("Network Error");
    expect(await listQueuedScores()).toEqual([]);
  });

  it("gives queued season-route entries an idempotency key", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    const response = await api.post("/scoring/seasons/s1/matches", { team_id: "t1", is_practice: true });
    const [entry] = await listQueuedScores();
    expect(entry.body.is_practice).toBe(true);
    expect(entry.id).toBe((response.data as { idempotency_key: string }).idempotency_key);
  });
});
