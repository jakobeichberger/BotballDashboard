/**
 * Live updates of an event over its WebSocket (/v1/public/events/{slug}/ws,
 * backend core/live.py). The stream only exists for events with a public view;
 * the authenticated pages use it to invalidate their queries and poll only
 * while it is unavailable.
 *
 * One socket per event is shared by every subscriber of the tab; it reconnects
 * with exponential backoff and jitter and closes when the last one leaves.
 */
import { backoffDelay } from "@/lib/backoff";

export interface LiveMessage {
  event: string;
  eventId?: string;
  payload?: Record<string, unknown>;
}

type Listener = (message: LiveMessage) => void;
type StatusListener = (connected: boolean) => void;

interface Channel {
  socket: WebSocket | null;
  listeners: Set<Listener>;
  statusListeners: Set<StatusListener>;
  connected: boolean;
  attempt: number;
  timer?: ReturnType<typeof setTimeout>;
  stopped: boolean;
}

/** Close code of the backend when nothing about the event is public. */
const NOT_PUBLIC = 1008;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

const channels = new Map<string, Channel>();

export function liveSocketUrl(slug: string): string {
  const base = import.meta.env.VITE_API_URL ?? "/api";
  const prefix = base.startsWith("http")
    ? base.replace(/^http/, "ws")
    : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${base}`;
  return `${prefix.replace(/\/$/, "")}/v1/public/events/${encodeURIComponent(slug)}/ws`;
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

function connect(slug: string, channel: Channel) {
  if (channel.stopped || typeof WebSocket === "undefined") return;
  let socket: WebSocket;
  try {
    socket = new WebSocket(liveSocketUrl(slug));
  } catch {
    scheduleReconnect(slug, channel);
    return;
  }
  channel.socket = socket;
  socket.onopen = () => {
    channel.attempt = 0;
    setConnected(channel, true);
  };
  socket.onmessage = (frame) => {
    const message = parseLiveMessage(frame.data);
    if (!message) return;
    if (message.event === "connection" && message.payload?.status === "disconnected") {
      setConnected(channel, false);
      return;
    }
    channel.listeners.forEach((listener) => listener(message));
  };
  socket.onclose = (event) => {
    channel.socket = null;
    setConnected(channel, false);
    // Not public (any more): polling takes over; no point in reconnecting.
    if (event.code === NOT_PUBLIC) return;
    scheduleReconnect(slug, channel);
  };
  socket.onerror = () => socket.close();
}

function scheduleReconnect(slug: string, channel: Channel) {
  if (channel.stopped) return;
  const delay = reconnectDelay(channel.attempt);
  channel.attempt += 1;
  channel.timer = setTimeout(() => connect(slug, channel), delay);
}

/**
 * Subscribe to the live stream of an event. `onStatus` reports whether the
 * socket is currently connected. Returns the unsubscribe function.
 */
export function subscribeLive(slug: string, listener: Listener, onStatus?: StatusListener): () => void {
  let channel = channels.get(slug);
  if (!channel) {
    channel = { socket: null, listeners: new Set(), statusListeners: new Set(), connected: false, attempt: 0, stopped: false };
    channels.set(slug, channel);
    connect(slug, channel);
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
    current.socket?.close();
    channels.delete(slug);
  };
}
