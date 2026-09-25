import { MutationObserver, onlineManager } from "@tanstack/react-query";
import { afterEach, describe, expect, it } from "vitest";
import { createQueryClient } from "@/lib/queryClient";

describe("createQueryClient", () => {
  afterEach(() => onlineManager.setOnline(true));

  it("runs mutations while offline so score entries reach the offline queue", async () => {
    onlineManager.setOnline(false);
    const client = createQueryClient();
    const observer = new MutationObserver(client, { mutationFn: async (value: number) => value * 2 });
    // With React Query's default network mode this promise would stay
    // pending (paused) until the browser is back online.
    await expect(observer.mutate(21)).resolves.toBe(42);
  });
});
