/**
 * Types and query hooks for the analytics, role-summary and calendar endpoints
 * under /dashboard. Local interfaces until generated.ts is regenerated.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface BoxSummary {
  n: number;
  min: number | null;
  q1: number | null;
  median: number | null;
  q3: number | null;
  max: number | null;
  mean: number | null;
}

// ── Deadlines ────────────────────────────────────────────────────────────────

export type DeadlineColor = "red" | "orange" | "green" | "blue" | "purple" | "gray";

export interface DeadlineEntry {
  id: string;
  title: string;
  kind: string;
  color: DeadlineColor | string;
  start: string;
  end: string | null;
  all_day: boolean;
  season_id: string;
  season_name: string;
  event_id: string | null;
  description: string | null;
  done: boolean | null;
}

export interface TimelinePhase {
  id: string;
  name: string;
  phase_type: string;
  starts_at: string | null;
  ends_at: string | null;
  status: "planned" | "active" | "finished" | string;
}

export interface TimelineEvent extends Omit<TimelinePhase, "phase_type"> {
  event_type: string;
  color: string;
  phases: TimelinePhase[];
}

export interface SeasonTimeline {
  season_id: string;
  season_name: string;
  season_year: number;
  events: TimelineEvent[];
}

export interface CalendarFeedStatus {
  active: boolean;
  created_at: string | null;
  last_used_at: string | null;
}

// ── Summary ──────────────────────────────────────────────────────────────────

export interface SummaryScheduledMatch {
  id: string;
  code: string;
  round_number: number;
  table_number: number | null;
  scheduled_at: string | null;
  status: string;
  phase_name: string | null;
  teams: Array<{ team_id: string | null; team_name: string | null }>;
}

export interface JurorSection {
  unconfirmed_count: number;
  unconfirmed: Array<{
    match_id: string;
    team_id: string;
    team_name: string;
    round_number: number;
    total_score: number;
    is_disqualified: boolean;
    created_at: string | null;
    entered_by_name: string | null;
    entered_by_team_member: boolean;
  }>;
  upcoming_matches: SummaryScheduledMatch[];
  open_scans_count: number;
  open_scans: Array<{ id: string; team_id: string; team_name: string; status: string; file_name: string; created_at: string | null }>;
}

export interface MentorTeam {
  team_id: string;
  team_name: string;
  seeding_rank: number | null;
  seed_score: number | null;
  seeding_teams: number;
  next_matches: SummaryScheduledMatch[];
  paper: { id: string; title: string; status: string; submitted_at: string | null; final_score: number | null } | null;
  print_jobs: {
    open: number;
    completed: number;
    recent: Array<{ id: string; file_name: string; status: string; created_at: string | null }>;
  };
  latest_scores: Array<{
    match_id: string;
    round_number: number;
    total_score: number;
    is_practice: boolean;
    is_disqualified: boolean;
    confirmed: boolean;
    created_at: string | null;
  }>;
}

export interface AdminSection {
  teams_registered: number;
  teams_checked_in: number;
  teams_scored: number;
  teams_with_paper: number;
  papers_total: number;
  reviews_pending: number;
  official_runs: number;
  practice_runs: number;
  unconfirmed_runs: number;
  de_results: number;
  doc_scores: number;
  print_queue: { pending: number; active: number; completed: number; failed: number };
  generated_at: string;
}

export interface DashboardSummary {
  event_id: string;
  juror: JurorSection | null;
  mentor: { teams: MentorTeam[] } | null;
  admin: AdminSection | null;
  deadlines: DeadlineEntry[];
}

// ── Performance ──────────────────────────────────────────────────────────────

export interface PerformanceRun {
  match_id: string;
  round_number: number;
  created_at: string | null;
  total_score: number;
  is_practice: boolean;
  is_disqualified: boolean;
  phase: string;
  phase_name: string | null;
  notes: string | null;
  confirmed: boolean;
}

export interface PerformanceField {
  key: string;
  label: string;
  team_avg: number | null;
  field_avg: number | null;
  field_best: number | null;
  delta: number | null;
  share_of_best: number | null;
}

export interface TeamPerformance {
  event_id: string;
  event_name: string;
  team_id: string;
  team_name: string;
  category: string;
  include_practice: boolean;
  runs: PerformanceRun[];
  summary: {
    official_runs: number;
    official_avg: number | null;
    official_best: number | null;
    practice_runs: number;
    practice_avg: number | null;
    practice_best: number | null;
    trend_per_run: number | null;
  };
  fields: PerformanceField[];
  strengths: string[];
  weaknesses: string[];
  phases: Array<BoxSummary & { phase: string }>;
  season_events: Array<{
    event_id: string;
    event_name: string;
    event_type: string;
    starts_at: string | null;
    practice_runs: number;
    practice_avg: number | null;
    official_runs: number;
    official_avg: number | null;
    official_best: number | null;
  }>;
  ranking_preview: {
    seeding_rank: number | null;
    seeding_score: number | null;
    seeding_teams: number;
    points_to_next_rank: number | null;
    overall_rank: number | null;
    overall_score: number | null;
    overall_teams: number;
  };
}

export interface PerformanceOverviewRow {
  team_id: string;
  team_name: string;
  team_number: string | null;
  official_runs: number;
  official_avg: number | null;
  official_best: number | null;
  practice_runs: number;
  practice_avg: number | null;
  trend_per_run: number | null;
  seeding_rank: number | null;
  last_run_at: string | null;
}

// ── Statistics ───────────────────────────────────────────────────────────────

export interface AnomalyReason {
  kind: string;
  message: string;
  severity: "error" | "warning" | string;
  score: number | null;
}

export interface Anomaly {
  match_id: string;
  team_id: string;
  team_name: string;
  round_number: number;
  total_score: number;
  is_practice: boolean;
  scheduled_match_id: string | null;
  confirmed: boolean;
  created_at: string | null;
  severity: "error" | "warning" | string;
  reasons: AnomalyReason[];
}

export interface EventStatistics {
  event_id: string;
  event_name: string;
  include_practice: boolean;
  overview: { runs: number; disqualified: number; teams: number; unconfirmed: number; total: BoxSummary | null };
  rounds: Array<BoxSummary & { round_number: number }>;
  fields: Array<BoxSummary & { key: string; label: string; zero_share: number | null }>;
  heatmap: {
    fields: Array<{ key: string; label: string }>;
    teams: Array<{ team_id: string; team_name: string; values: Array<{ key: string; avg: number | null; ratio: number | null }> }>;
  };
  trend: {
    rounds: Array<{ round_number: number; mean: number | null; median: number | null }>;
    teams: Array<{
      team_id: string;
      team_name: string;
      points: Array<{ round_number: number; total_score: number; match_id: string }>;
      slope: number | null;
    }>;
  };
  anomalies: Anomaly[];
}

// ── History ──────────────────────────────────────────────────────────────────

export interface TeamHistoryRow {
  team_id: string;
  team_name: string;
  team_number: string | null;
  season_id: string;
  season_name: string;
  season_year: number;
  event_id: string;
  event_name: string;
  event_type: string;
  starts_at: string | null;
  category: string;
  seeding_rank: number | null;
  seeding_score: number | null;
  seeding_teams: number;
  best_score: number | null;
  official_runs: number;
  official_avg: number | null;
  overall_rank: number | null;
  overall_score: number | null;
  overall_teams: number;
  de_score: number | null;
  doc_score: number | null;
  paper_score: number | null;
  practice_runs?: number | null;
  practice_avg?: number | null;
}

// ── Hooks ────────────────────────────────────────────────────────────────────

export function useDashboardSummary(eventId?: string) {
  return useQuery<DashboardSummary>({
    queryKey: ["dashboard", "summary", eventId],
    queryFn: async () => (await api.get("/dashboard/summary", { params: { event_id: eventId } })).data,
    enabled: !!eventId,
  });
}

export function useTeamHistory(teamId?: string) {
  return useQuery<TeamHistoryRow[]>({
    queryKey: ["dashboard", "team-history", teamId],
    queryFn: async () => (await api.get(`/dashboard/teams/${teamId}/history`)).data,
    enabled: !!teamId,
  });
}

export function usePerformanceOverview(eventId?: string) {
  return useQuery<PerformanceOverviewRow[]>({
    queryKey: ["dashboard", "performance", eventId],
    queryFn: async () => (await api.get(`/dashboard/events/${eventId}/performance`)).data,
    enabled: !!eventId,
  });
}

export function useTeamPerformance(eventId?: string, teamId?: string, includePractice = true) {
  return useQuery<TeamPerformance>({
    queryKey: ["dashboard", "performance", eventId, teamId, includePractice],
    queryFn: async () =>
      (
        await api.get(`/dashboard/events/${eventId}/teams/${teamId}/performance`, {
          params: { include_practice: includePractice },
        })
      ).data,
    enabled: !!eventId && !!teamId,
  });
}

export function useEventStatistics(eventId?: string, includePractice = false) {
  return useQuery<EventStatistics>({
    queryKey: ["dashboard", "statistics", eventId, includePractice],
    queryFn: async () =>
      (await api.get(`/dashboard/events/${eventId}/statistics`, { params: { include_practice: includePractice } })).data,
    enabled: !!eventId,
  });
}

export function useDeadlines(seasonId?: string) {
  return useQuery<DeadlineEntry[]>({
    queryKey: ["dashboard", "deadlines", seasonId ?? "relevant"],
    queryFn: async () =>
      (await api.get("/dashboard/deadlines", { params: seasonId ? { season_id: seasonId } : {} })).data,
  });
}

export function useSeasonTimeline(seasonId?: string) {
  return useQuery<SeasonTimeline>({
    queryKey: ["dashboard", "timeline", seasonId],
    queryFn: async () => (await api.get(`/dashboard/seasons/${seasonId}/timeline`)).data,
    enabled: !!seasonId,
  });
}

// ── Formatting helpers shared by the analytics views ─────────────────────────

export function fmtNum(value: number | null | undefined, digits = 1): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

export const PHASE_LABELS: Record<string, string> = {
  practice: "Übung",
  seeding: "Seeding",
  double_seeding: "Double Seeding",
  elimination: "Double Elimination",
  double_elimination: "Double Elimination",
  alliance: "Alliance",
  final: "Finale",
};

/** Whole days from today until `iso` (negative = past). */
export function daysUntil(iso: string, now: Date = new Date()): number {
  const target = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfTarget = new Date(target.getFullYear(), target.getMonth(), target.getDate());
  return Math.round((startOfTarget.getTime() - startOfToday.getTime()) / 86_400_000);
}
