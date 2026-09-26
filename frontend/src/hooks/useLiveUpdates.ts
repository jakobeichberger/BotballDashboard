import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useEvent } from "@/hooks/useEvents";
import { subscribeEventLive, subscribeLive, type LiveMessage } from "@/lib/liveSocket";
import { useAuthStore } from "@/store/authStore";
import type { EventSummary } from "@/api/types";

/**
 * Query keys (first element) a live event makes stale. Only mounted queries
 * refetch; the others are fetched fresh when they are used next.
 */
const INVALIDATES: Record<string, readonly string[]> = {
  ranking_updated: ["event-ranking", "ranking-extended", "overall-ranking", "de-results", "aerial-ranking", "matches", "event-matches", "h2h-outcome", "de-placement"],
  schedule_updated: ["event-schedule", "event-bracket", "h2h-outcome"],
  announcement_published: ["announcements"],
  announcement_removed: ["announcements"],
  awards_updated: ["event-awards", "public-awards"],
};

/**
 * Ranking refreshes are spread out: every committed score sends
 * ranking_updated to every open screen at once, right after the server
 * dropped its ranking cache. Waiting a random 300–1000 ms (and bundling the
 * events that arrive meanwhile into one refetch) keeps all clients from
 * hitting the fresh cache miss in the same instant.
 */
export const RANKING_REFRESH_MIN_MS = 300;
export const RANKING_REFRESH_JITTER_MS = 700;

export function rankingRefreshDelay(random: () => number = Math.random): number {
  return RANKING_REFRESH_MIN_MS + Math.floor(random() * RANKING_REFRESH_JITTER_MS);
}

/** Events whose refetch is delayed and bundled (see rankingRefreshDelay). */
const DEFERRED = new Set(["ranking_updated"]);

/** Fallback polling while the live stream is unavailable. */
export const FALLBACK_POLL_MS = 15_000;

function hasLiveStream(event: EventSummary | undefined): event is EventSummary {
  return !!event?.slug && (event.public_scoreboard || event.public_schedule || event.public_results || event.public_announcements);
}

/**
 * Keeps the queries of an event current through a live WebSocket: the
 * authenticated stream of the event while signed in (any event the user may
 * read), else the public stream when the event has one. `live` is false while
 * the stream is not connected; pages then poll (`pollWhileOffline`).
 */
export function useLiveUpdates(eventId: string | undefined): { live: boolean } {
  const queryClient = useQueryClient();
  // Only whether there is a session: a refreshed token is handed to the open
  // socket by lib/liveSocket, without reconnecting.
  const signedIn = useAuthStore((state) => !!state.accessToken);
  const { data: event } = useEvent(eventId);
  const slug = hasLiveStream(event) ? event.slug : null;
  const authenticatedId = signedIn && eventId ? eventId : null;
  const publicSlug = authenticatedId ? null : slug;
  const [live, setLive] = useState(false);

  useEffect(() => {
    // Without a stream `live` is reported false below; subscribing reports
    // the current status of the new stream right away.
    if (!authenticatedId && !publicSlug) return;
    const invalidate = (keys: Iterable<string>) => {
      const wanted = new Set(keys);
      void queryClient.invalidateQueries({ predicate: (query) => wanted.has(String(query.queryKey[0])) });
    };
    const pending = new Set<string>();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const flush = () => {
      timer = null;
      const keys = [...pending];
      pending.clear();
      invalidate(keys);
    };
    const onMessage = (message: LiveMessage) => {
      const keys = INVALIDATES[message.event];
      if (!keys) return;
      if (!DEFERRED.has(message.event)) {
        invalidate(keys);
        return;
      }
      keys.forEach((key) => pending.add(key));
      // The first event of a burst starts the timer; later ones ride along.
      timer ??= setTimeout(flush, rankingRefreshDelay());
    };
    const unsubscribe = authenticatedId
      ? subscribeEventLive(authenticatedId, onMessage, setLive)
      : subscribeLive(publicSlug!, onMessage, setLive);
    return () => {
      if (timer !== null) clearTimeout(timer);
      unsubscribe();
    };
  }, [authenticatedId, publicSlug, queryClient]);

  return { live: (!!authenticatedId || !!publicSlug) && live };
}

/** refetchInterval: none while live updates arrive, `ms` otherwise. */
export function pollWhileOffline(live: boolean, ms = FALLBACK_POLL_MS): number | false {
  return live ? false : ms;
}
