/**
 * Live updates of an event over a WebSocket (backend core/live.py):
 *
 * - `subscribeEventLive(eventId)`: the authenticated stream
 *   (/v1/events/{id}/ws, modules/events/live_socket.py) of any event the user
 *   may read. The access token goes in the first message, never in the URL,
 *   and is sent again whenever the session gets a new one.
 * - `subscribeLive(slug)`: the public stream (/v1/public/events/{slug}/ws),
 *   which only exists for events with a public view.
 *
 * The pages use them to invalidate their queries and poll only while the
 * stream is unavailable. One socket per stream is shared by every subscriber
 * of the tab; it reconnects with exponential backoff and jitter and closes
 * when the last one leaves.
 */
import { backoffDelay } from "@/lib/backoff";
import { refreshSession } from "@/lib/sessionRefresh";
import { useAuthStore } from "@/store/authStore";

export interface LiveMessage {
  event: string;
  eventId?: string;
  payload?: Record<string, unknown>;
}

type Listener = (message: LiveMessage) => void;
type StatusListener = (connected: boolean) => void;

type LiveTarget = { kind: "public"; slug: string } | { kind: "event"; eventId: string };

interface Channel {
  key: string;
  target: LiveTarget;
  socket: WebSocket | null;
  listeners: Set<Listener>;
  statusListeners: Set<StatusListener>;
  connected: boolean;
  attempt: number;
  timer?: ReturnType<typeof setTimeout>;
  stopped: boolean;
  /** Authenticated stream: waiting for a (new) access token to connect. */
  awaitingToken: boolean;
  /** Authenticated stream: stops following the session's access token. */
  unfollowToken?: () => void;
}

/** Close code of the public stream when nothing about the event is public. */
const NOT_PUBLIC = 1008;
/** Close codes of the authenticated stream (backend modules/events/live_socket.py). */
export const LIVE_CLOSE = {
  unauthorized: 4401,
  forbidden: 4403,
  notFound: 4404,
} as const;
/** WebSocket.OPEN (read from the instance's class would break under test doubles). */
const OPEN = 1;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

const channels = new Map<string, Channel>();

function socketBase(): string {
  const base = import.meta.env.VITE_API_URL ?? "/api";
  const prefix = base.startsWith("http")
    ? base.replace(/^http/, "ws")
    : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${base}`;
  return prefix.replace(/\/$/, "");
}

export function liveSocketUrl(slug: string): string {
  return `${socketBase()}/v1/public/events/${encodeURIComponent(slug)}/ws`;
}

export function eventLiveSocketUrl(eventId: string): string {
  return `${socketBase()}/v1/events/${encodeURIComponent(eventId)}/ws`;
}

/** A frame of the live stream, or null for anything malformed. */
export function parseLiveMessage(raw: unknown): LiveMessage | null {
  if (typeof raw !== "string") return null;
  try {
    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== "object" || typeof (data as LiveMessage).event !== "string") return null;
    return data as LiveMessage;
  } catch {
    return null;
  }
}

/** Reconnect delay after `attempt` failed connections (1 s … 30 s, jittered). */
export function reconnectDelay(attempt: number, random = Math.random): number {
  return backoffDelay(attempt, RECONNECT_BASE_MS, RECONNECT_MAX_MS, random);
}

function setConnected(channel: Channel, connected: boolean) {
  if (channel.connected === connected) return;
  channel.connected = connected;
  channel.statusListeners.forEach((listener) => listener(connected));
}

function sendToken(socket: WebSocket, token: string) {
  try {
    socket.send(JSON.stringify({ type: "auth", token }));
  } catch {
    // Not open (any more): onclose reconnects and authenticates again.
  }
}

function connect(channel: Channel) {
  if (channel.stopped || typeof WebSocket === "undefined") return;
  const { target } = channel;
  const token = useAuthStore.getState().accessToken;
  if (target.kind === "event" && !token) {
    // Signed out or offline session: connect once a token arrives.
    channel.awaitingToken = true;
    return;
  }
  channel.awaitingToken = false;
  let socket: WebSocket;
  try {
    socket = new WebSocket(target.kind === "event" ? eventLiveSocketUrl(target.eventId) : liveSocketUrl(target.slug));
  } catch {
    scheduleReconnect(channel);
    return;
  }
  channel.socket = socket;
  socket.onopen = () => {
    if (target.kind === "event") {
      // Connected only once the server accepted the token ("connection").
      sendToken(socket, useAuthStore.getState().accessToken ?? "");
      return;
    }
    channel.attempt = 0;
    setConnected(channel, true);
  };
  socket.onmessage = (frame) => {
    const message = parseLiveMessage(frame.data);
    if (!message) return;
    if (message.event === "connection") {
      if (message.payload?.status === "disconnected") setConnected(channel, false);
      else if (message.payload?.status === "connected" && target.kind === "event") {
        channel.attempt = 0;
        setConnected(channel, true);
      }
      return;
    }
    if (message.event === "auth" || message.event === "pong") return;
    channel.listeners.forEach((listener) => listener(message));
  };
  socket.onclose = (event) => {
    if (channel.socket === socket) channel.socket = null;
    setConnected(channel, false);
    // Unsubscribed, or closed on sign-out (a new token reconnects).
    if (channel.stopped || channel.awaitingToken) return;
    // Not public (any more), no permission or no such event: polling takes
    // over (and reports the error); reconnecting would not help.
    if (event.code === NOT_PUBLIC || event.code === LIVE_CLOSE.forbidden || event.code === LIVE_CLOSE.notFound) return;
    if (event.code === LIVE_CLOSE.unauthorized) {
      void renewAndReconnect(channel);
      return;
    }
    scheduleReconnect(channel);
  };
  socket.onerror = () => socket.close();
}

/** The token was refused or expired: get a new one, then connect again. */
async function renewAndReconnect(channel: Channel) {
  const outcome = await refreshSession();
  if (channel.stopped) return;
  if (outcome.status === "unauthorized") {
    // The session is over; follow the store until someone signs in again.
    channel.awaitingToken = true;
    return;
  }
  // A new token (or the server was unreachable): try again after a backoff,
  // so a server that keeps refusing is not hammered.
  scheduleReconnect(channel);
}

function scheduleReconnect(channel: Channel) {
  if (channel.stopped) return;
  if (channel.timer) clearTimeout(channel.timer);
  const delay = reconnectDelay(channel.attempt);
  channel.attempt += 1;
  channel.timer = setTimeout(() => {
    channel.timer = undefined;
    connect(channel);
  }, delay);
}

/** Authenticated streams re-send the token whenever the session gets a new one. */
function followToken(channel: Channel): () => void {
  return useAuthStore.subscribe((state, previous) => {
    if (state.accessToken === previous.accessToken || channel.stopped) return;
    const token = state.accessToken;
    if (!token) {
      // Signed out: close now; a later sign-in reconnects.
      channel.awaitingToken = true;
      if (channel.timer) clearTimeout(channel.timer);
      channel.timer = undefined;
      channel.socket?.close();
      return;
    }
    if (channel.socket && channel.socket.readyState === OPEN) {
      sendToken(channel.socket, token);
    } else if (channel.awaitingToken) {
      channel.attempt = 0;
      connect(channel);
    }
  });
}

function subscribe(target: LiveTarget, listener: Listener, onStatus?: StatusListener): () => void {
  const key = target.kind === "event" ? `event:${target.eventId}` : `public:${target.slug}`;
  let channel = channels.get(key);
  if (!channel) {
    channel = {
      key,
      target,
      socket: null,
      listeners: new Set(),
      statusListeners: new Set(),
      connected: false,
      attempt: 0,
      stopped: false,
      awaitingToken: false,
    };
    channels.set(key, channel);
    if (target.kind === "event") channel.unfollowToken = followToken(channel);
    connect(channel);
  }
  const current = channel;
  current.listeners.add(listener);
  if (onStatus) {
    current.statusListeners.add(onStatus);
    onStatus(current.connected);
  }
  return () => {
    current.listeners.delete(listener);
    if (onStatus) current.statusListeners.delete(onStatus);
    if (current.listeners.size > 0) return;
    current.stopped = true;
    if (current.timer) clearTimeout(current.timer);
    current.unfollowToken?.();
    current.socket?.close();
    channels.delete(current.key);
  };
}

/**
 * Subscribe to the public live stream of an event. `onStatus` reports whether
 * the socket is currently connected. Returns the unsubscribe function.
 */
export function subscribeLive(slug: string, listener: Listener, onStatus?: StatusListener): () => void {
  return subscribe({ kind: "public", slug }, listener, onStatus);
}

/**
 * Subscribe to the authenticated live stream of an event (signed-in pages).
 * `onStatus` reports whether the stream is connected and authenticated.
 * Returns the unsubscribe function.
 */
export function subscribeEventLive(eventId: string, listener: Listener, onStatus?: StatusListener): () => void {
  return subscribe({ kind: "event", eventId }, listener, onStatus);
}
