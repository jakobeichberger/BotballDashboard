import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useEvent } from "@/hooks/useEvents";
import { subscribeLive } from "@/lib/liveSocket";
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
};

/** Fallback polling while the live stream is unavailable. */
export const FALLBACK_POLL_MS = 15_000;

function hasLiveStream(event: EventSummary | undefined): event is EventSummary {
  return !!event?.slug && (event.public_scoreboard || event.public_schedule || event.public_results || event.public_announcements);
}

/**
 * Keeps the queries of an event current through its live WebSocket when the
 * event has one (it is public). `live` is false while the stream is not
 * connected; pages then poll (`pollWhileOffline`).
 */
export function useLiveUpdates(eventId: string | undefined): { live: boolean } {
  const queryClient = useQueryClient();
  const { data: event } = useEvent(eventId);
  const slug = hasLiveStream(event) ? event.slug : null;
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (!slug) {
      setLive(false);
      return;
    }
    return subscribeLive(
      slug,
      (message) => {
        const keys = INVALIDATES[message.event];
        if (keys) void queryClient.invalidateQueries({ predicate: (query) => keys.includes(String(query.queryKey[0])) });
      },
      setLive,
    );
  }, [slug, queryClient]);

  return { live: !!slug && live };
}

/** refetchInterval: none while live updates arrive, `ms` otherwise. */
export function pollWhileOffline(live: boolean, ms = FALLBACK_POLL_MS): number | false {
  return live ? false : ms;
}
