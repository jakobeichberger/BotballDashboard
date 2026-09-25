import { describe, expect, it } from "vitest";
import { isOfflineCacheableApiRequest } from "@/lib/offlineCache";

const EVENT = "0b6f7d2e-8a1c-4e5f-9a3b-1c2d3e4f5a6b";

describe("service worker API cache rule", () => {
  it("keeps the data the scoring form needs", () => {
    for (const path of [
      `/api/v1/events/${EVENT}`,
      `/api/v1/events/${EVENT}/scoring-schema`,
      `/api/v1/events/${EVENT}/registrations`,
      `/api/v1/events/${EVENT}/schedule`,
      `/api/v1/events/${EVENT}/modules`,
      "/api/teams",
      "/api/auth/me",
      `/api/scoring/seasons/${EVENT}/schema`,
    ]) {
      expect(isOfflineCacheableApiRequest("GET", path)).toBe(true);
    }
  });

  it("never caches writes or unrelated reads", () => {
    expect(isOfflineCacheableApiRequest("POST", `/api/v1/events/${EVENT}/matches`)).toBe(false);
    expect(isOfflineCacheableApiRequest("GET", "/api/papers")).toBe(false);
    expect(isOfflineCacheableApiRequest("GET", "/api/auth/users")).toBe(false);
    expect(isOfflineCacheableApiRequest("GET", `/api/v1/events/${EVENT}/score-sheet-scans`)).toBe(false);
  });
});
