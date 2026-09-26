import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pollWhileOffline, rankingRefreshDelay, useLiveUpdates } from "@/hooks/useLiveUpdates";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));

class FakeSocket {
  static last: FakeSocket | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((frame: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  sent: string[] = [];
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
}

beforeEach(() => {
  FakeSocket.last = null;
  useAuthStore.setState({ accessToken: null });
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  useAuthStore.setState({ accessToken: null });
});

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

    vi.spyOn(Math, "random").mockReturnValue(0);
    const ranking = JSON.stringify({ event: "ranking_updated", eventId: "ev1" });
    act(() => {
      FakeSocket.last!.onmessage?.({ data: ranking });
      FakeSocket.last!.onmessage?.({ data: ranking });
      FakeSocket.last!.onmessage?.({ data: ranking });
    });
    // Not in the same instant as every other screen: delayed, then bundled.
    expect(invalidate).not.toHaveBeenCalled();
    await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(1), { timeout: 2000 });
    const { predicate } = invalidate.mock.calls[0][0] as unknown as { predicate: (query: { queryKey: unknown[] }) => boolean };
    expect(predicate({ queryKey: ["event-ranking", "ev1"] })).toBe(true);
    expect(predicate({ queryKey: ["teams"] })).toBe(false);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(invalidate).toHaveBeenCalledTimes(1);
    vi.mocked(Math.random).mockRestore();

    act(() => FakeSocket.last!.close());
    expect(result.current.live).toBe(false);
  });

  it("spreads ranking refreshes over 300–1000 ms", () => {
    expect(rankingRefreshDelay(() => 0)).toBe(300);
    expect(rankingRefreshDelay(() => 0.999)).toBeLessThan(1000);
    expect(rankingRefreshDelay(() => 0.5)).toBe(650);
  });

  it("drops a pending ranking refresh on unmount", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { invalidate, unmount } = setup({ id: "ev1", slug: "ecer", public_scoreboard: true });
      await vi.waitFor(() => expect(FakeSocket.last).not.toBeNull());
      act(() => FakeSocket.last!.onopen?.());
      act(() => FakeSocket.last!.onmessage?.({ data: JSON.stringify({ event: "ranking_updated", eventId: "ev1" }) }));
      unmount();
      vi.advanceTimersByTime(2000);
      expect(invalidate).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("falls back to polling for events without a public stream", async () => {
    const { result } = setup({ id: "ev1", slug: "internal", public_scoreboard: false, public_schedule: false, public_results: false, public_announcements: false });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(FakeSocket.last).toBeNull();
    expect(result.current.live).toBe(false);
  });

  it("uses the authenticated stream of any event while signed in", async () => {
    useAuthStore.setState({ accessToken: "access-token" });
    const internal = { id: "ev1", slug: "internal", public_scoreboard: false, public_schedule: false, public_results: false, public_announcements: false };
    const { result, invalidate } = setup(internal);
    await waitFor(() => expect(FakeSocket.last).not.toBeNull());
    const socket = FakeSocket.last!;
    expect(socket.url).toMatch(/\/v1\/events\/ev1\/ws$/);

    act(() => socket.onopen?.());
    expect(JSON.parse(socket.sent[0])).toEqual({ type: "auth", token: "access-token" });
    // Still polling until the server accepted the token.
    expect(result.current.live).toBe(false);
    act(() => socket.onmessage?.({ data: JSON.stringify({ event: "connection", payload: { status: "connected" } }) }));
    expect(result.current.live).toBe(true);
    expect(pollWhileOffline(result.current.live)).toBe(false);

    act(() => socket.onmessage?.({ data: JSON.stringify({ event: "schedule_updated", eventId: "ev1" }) }));
    const { predicate } = invalidate.mock.calls[0][0] as unknown as { predicate: (query: { queryKey: unknown[] }) => boolean };
    expect(predicate({ queryKey: ["event-schedule", "ev1"] })).toBe(true);

    act(() => socket.onclose?.({ code: 1013 }));
    expect(result.current.live).toBe(false);
  });
});
