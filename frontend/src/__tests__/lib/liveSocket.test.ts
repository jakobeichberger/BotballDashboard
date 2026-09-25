import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LIVE_CLOSE, parseLiveMessage, reconnectDelay, subscribeEventLive, subscribeLive } from "@/lib/liveSocket";
import { refreshSession } from "@/lib/sessionRefresh";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/sessionRefresh", () => ({ refreshSession: vi.fn() }));

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((frame: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  readyState = 0;
  sent: string[] = [];
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  /** Server side: accept the connection. */
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  /** Server side: send a frame. */
  push(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
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
  useAuthStore.setState({ accessToken: null });
  vi.mocked(refreshSession).mockReset();
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

describe("authenticated event stream", () => {
  const connected = { event: "connection", payload: { status: "connected" } };

  it("authenticates with the first message and reports connected only once accepted", () => {
    useAuthStore.setState({ accessToken: "token-1" });
    const messages: string[] = [];
    const status: boolean[] = [];
    const stop = subscribeEventLive("ev 1", (message) => messages.push(message.event), (up) => status.push(up));
    const [socket] = FakeSocket.instances;
    // The event id is in the path, the token never is.
    expect(socket.url).toMatch(/\/v1\/events\/ev%201\/ws$/);
    expect(socket.url).not.toContain("token");

    socket.open();
    expect(socket.sent.map((frame) => JSON.parse(frame))).toEqual([{ type: "auth", token: "token-1" }]);
    expect(status).toEqual([false]);
    socket.push(connected);
    expect(status).toEqual([false, true]);

    socket.push({ event: "ranking_updated" });
    socket.push({ event: "pong" });
    socket.push({ event: "auth", payload: { status: "ok" } });
    expect(messages).toEqual(["ranking_updated"]);

    // A refreshed token goes to the open socket; no reconnect.
    useAuthStore.setState({ accessToken: "token-2" });
    expect(JSON.parse(socket.sent[1])).toEqual({ type: "auth", token: "token-2" });
    expect(FakeSocket.instances).toHaveLength(1);
    stop();
  });

  it("waits for a token and closes on sign-out", () => {
    const status: boolean[] = [];
    const stop = subscribeEventLive("ev1", () => undefined, (up) => status.push(up));
    expect(FakeSocket.instances).toHaveLength(0);

    useAuthStore.setState({ accessToken: "token-1" });
    expect(FakeSocket.instances).toHaveLength(1);
    FakeSocket.instances[0].open();
    FakeSocket.instances[0].push(connected);

    useAuthStore.setState({ accessToken: null });
    expect(FakeSocket.instances[0].closed).toBe(true);
    expect(status).toEqual([false, true, false]);
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);

    useAuthStore.setState({ accessToken: "token-3" });
    expect(FakeSocket.instances).toHaveLength(2);
    stop();
  });

  it("renews the session when the token is refused, then reconnects", async () => {
    useAuthStore.setState({ accessToken: "stale" });
    vi.mocked(refreshSession).mockImplementation(async () => {
      useAuthStore.setState({ accessToken: "fresh" });
      return { status: "ok", token: "fresh" };
    });
    const stop = subscribeEventLive("ev1", () => undefined);
    FakeSocket.instances[0].open();
    FakeSocket.instances[0].drop(LIVE_CLOSE.unauthorized);
    await vi.waitFor(() => expect(refreshSession).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(FakeSocket.instances).toHaveLength(2);
    FakeSocket.instances[1].open();
    expect(JSON.parse(FakeSocket.instances[1].sent[0])).toEqual({ type: "auth", token: "fresh" });
    stop();
  });

  it("stops after a rejected refresh until someone signs in again", async () => {
    useAuthStore.setState({ accessToken: "stale" });
    vi.mocked(refreshSession).mockResolvedValue({ status: "unauthorized" });
    const stop = subscribeEventLive("ev1", () => undefined);
    FakeSocket.instances[0].drop(LIVE_CLOSE.unauthorized);
    await vi.waitFor(() => expect(refreshSession).toHaveBeenCalled());
    await vi.advanceTimersByTimeAsync(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
    useAuthStore.setState({ accessToken: "after-login" });
    expect(FakeSocket.instances).toHaveLength(2);
    stop();
  });

  it.each([LIVE_CLOSE.forbidden, LIVE_CLOSE.notFound])("gives up on close code %i (polling takes over)", (code) => {
    useAuthStore.setState({ accessToken: "token" });
    const stop = subscribeEventLive("ev1", () => undefined);
    FakeSocket.instances[0].drop(code);
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(refreshSession).not.toHaveBeenCalled();
    stop();
  });

  it("reconnects with backoff after the server lost its subscription", () => {
    useAuthStore.setState({ accessToken: "token" });
    const stop = subscribeEventLive("ev1", () => undefined);
    FakeSocket.instances[0].drop(1013);
    vi.advanceTimersByTime(30_000);
    expect(FakeSocket.instances).toHaveLength(2);
    stop();
    expect(FakeSocket.instances[1].closed).toBe(true);
  });
});
