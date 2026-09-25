import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pollWhileOffline, useLiveUpdates } from "@/hooks/useLiveUpdates";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));

class FakeSocket {
  static last: FakeSocket | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((frame: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
}

beforeEach(() => {
  FakeSocket.last = null;
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => vi.unstubAllGlobals());

function setup(event: Record<string, unknown>) {
  (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: event });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { invalidate, ...renderHook(() => useLiveUpdates("ev1"), { wrapper }) };
}

describe("useLiveUpdates", () => {
  it("invalidates ranking queries on ranking_updated and stops polling while connected", async () => {
    const { result, invalidate } = setup({ id: "ev1", slug: "ecer", public_scoreboard: true });
    await waitFor(() => expect(FakeSocket.last).not.toBeNull());
    expect(result.current.live).toBe(false);
    expect(pollWhileOffline(result.current.live)).toBe(15_000);

    act(() => FakeSocket.last!.onopen?.());
    expect(result.current.live).toBe(true);
    expect(pollWhileOffline(result.current.live)).toBe(false);

    act(() => FakeSocket.last!.onmessage?.({ data: JSON.stringify({ event: "ranking_updated", eventId: "ev1" }) }));
    const { predicate } = invalidate.mock.calls[0][0] as unknown as { predicate: (query: { queryKey: unknown[] }) => boolean };
    expect(predicate({ queryKey: ["event-ranking", "ev1"] })).toBe(true);
    expect(predicate({ queryKey: ["teams"] })).toBe(false);

    act(() => FakeSocket.last!.close());
    expect(result.current.live).toBe(false);
  });

  it("falls back to polling for events without a public stream", async () => {
    const { result } = setup({ id: "ev1", slug: "internal", public_scoreboard: false, public_schedule: false, public_results: false, public_announcements: false });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(FakeSocket.last).toBeNull();
    expect(result.current.live).toBe(false);
  });
});
