import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseLiveMessage, reconnectDelay, subscribeLive } from "@/lib/liveSocket";

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((frame: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    this.onclose?.({ code: 1000 });
  }
  /** Server side: drop the connection. */
  drop(code = 1006) {
    this.closed = true;
    this.onclose?.({ code });
  }
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("live socket", () => {
  it("ignores malformed frames instead of throwing", () => {
    expect(parseLiveMessage("{not json")).toBeNull();
    expect(parseLiveMessage(JSON.stringify({ payload: {} }))).toBeNull();
    expect(parseLiveMessage(new ArrayBuffer(2))).toBeNull();
    expect(parseLiveMessage(JSON.stringify({ event: "ranking_updated" }))).toEqual({ event: "ranking_updated" });
  });

  it("backs off exponentially with jitter up to 30 s", () => {
    expect(reconnectDelay(0, () => 0)).toBe(500);
    expect(reconnectDelay(0, () => 1)).toBe(1000);
    expect(reconnectDelay(3, () => 1)).toBe(8000);
    expect(reconnectDelay(10, () => 1)).toBe(30_000);
  });

  it("shares one socket, reports its status and reconnects after a drop", () => {
    const messages: string[] = [];
    const status: boolean[] = [];
    const stopA = subscribeLive("ecer", (message) => messages.push(message.event), (connected) => status.push(connected));
    const stopB = subscribeLive("ecer", () => undefined);
    expect(FakeSocket.instances).toHaveLength(1);
    const socket = FakeSocket.instances[0];
    expect(socket.url).toMatch(/\/v1\/public\/events\/ecer\/ws$/);

    socket.onopen?.();
    socket.onmessage?.({ data: "garbage" });
    socket.onmessage?.({ data: JSON.stringify({ event: "ranking_updated" }) });
    expect(messages).toEqual(["ranking_updated"]);
    expect(status).toEqual([false, true]);

    socket.drop();
    expect(status).toEqual([false, true, false]);
    vi.advanceTimersByTime(30_000);
    expect(FakeSocket.instances).toHaveLength(2);

    stopA();
    stopB();
    expect(FakeSocket.instances[1].closed).toBe(true);
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("does not reconnect when the event is not public", () => {
    const stop = subscribeLive("private", () => undefined);
    FakeSocket.instances[0].drop(1008);
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
    stop();
  });
});
