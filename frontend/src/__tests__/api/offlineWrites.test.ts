import { afterEach, describe, expect, it } from "vitest";
import { api } from "@/lib/api";

describe("online-only write protection", () => {
  afterEach(() => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
  });

  it("rejects a mutation before it reaches the network while offline", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    await expect(api.post("/offline-test", {})).rejects.toThrow("OFFLINE_WRITE_BLOCKED");
  });
});
