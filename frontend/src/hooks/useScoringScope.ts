import { useQuery } from "@tanstack/react-query";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";

/** The season fields the scoring pages read. */
export interface ScoringSeason {
  id: string;
  year?: number;
  use_seeding?: boolean;
  use_double_elimination?: boolean;
  use_paper_scoring?: boolean;
  use_documentation_scoring?: boolean;
  use_aerial?: boolean;
  active_categories?: string[];
}

export interface ScoringScope {
  /** The event results are read from and written to (undefined outside /events/:eventId). */
  eventId?: string;
  seasonId?: string;
  season?: ScoringSeason;
  /**
   * API prefix for the result resources (de-results, doc-scores, aerial-…,
   * ranking/…) of the event. Undefined outside /events/:eventId: results only
   * exist per event (the season-scoped result routes were removed).
   */
  base?: string;
}

/**
 * Where scoring pages read and write results.
 *
 * Results are recorded per event, so a page under /events/:eventId must use
 * that event — not the season's first event, which the season routes default to
 * (with an ECER and a GCER in one season the results would land in the wrong one).
 */
export function useScoringScope(): ScoringScope {
  const { eventId } = useParams();
  const [searchParams] = useSearchParams();
  const seasonParam = searchParams.get("season_id") ?? "";

  const { data: event } = useQuery<{ id: string; season_id: string }>({
    queryKey: ["events", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}`)).data,
    enabled: !!eventId,
  });

  const { data: activeSeason } = useQuery<ScoringSeason | null>({
    queryKey: ["seasons", "active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
    enabled: !eventId,
  });

  const seasonId = eventId ? event?.season_id : seasonParam || activeSeason?.id;

  const { data: eventSeason } = useQuery<ScoringSeason>({
    queryKey: ["seasons", seasonId],
    queryFn: async () => (await api.get(`/seasons/${seasonId}`)).data,
    enabled: !!eventId && !!seasonId,
  });

  const season = eventId ? eventSeason : activeSeason;
  const base = eventId ? `/scoring/events/${eventId}` : undefined;
  return { eventId, seasonId, season: season ?? undefined, base };
}
