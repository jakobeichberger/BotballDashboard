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
    if (!authenticatedId && !publicSlug) {
      setLive(false);
      return;
    }
    const onMessage = (message: LiveMessage) => {
      const keys = INVALIDATES[message.event];
      if (keys) void queryClient.invalidateQueries({ predicate: (query) => keys.includes(String(query.queryKey[0])) });
    };
    return authenticatedId
      ? subscribeEventLive(authenticatedId, onMessage, setLive)
      : subscribeLive(publicSlug!, onMessage, setLive);
  }, [authenticatedId, publicSlug, queryClient]);

  return { live: (!!authenticatedId || !!publicSlug) && live };
}

/** refetchInterval: none while live updates arrive, `ms` otherwise. */
export function pollWhileOffline(live: boolean, ms = FALLBACK_POLL_MS): number | false {
  return live ? false : ms;
}
