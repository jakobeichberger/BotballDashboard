export interface EventSummary {
  id: string;
  season_id: string;
  name: string;
  slug: string;
  event_type: string;
  timezone: string;
  venue: string | null;
  starts_at: string | null;
  ends_at: string | null;
  status: string;
  active_modules: string[];
  public_scoreboard: boolean;
  public_schedule: boolean;
  public_results: boolean;
  public_announcements: boolean;
  table_count: number;
  notes?: string | null;
}

export interface EventRegistration {
  id: string;
  event_id: string;
  team_id: string;
  competition_level_id: string | null;
  category: string;
  seed_number: number | null;
  checked_in_at: string | null;
  notes: string | null;
}

export interface EventPhase {
  id: string;
  event_id: string;
  name: string;
  phase_type: string;
  sort_order: number;
  status: string;
  rounds: number;
  starts_at: string | null;
  ends_at: string | null;
  settings: Record<string, unknown>;
}

export interface ScheduledMatch {
  id: string;
  event_id: string;
  phase_id: string;
  code: string;
  round_number: number;
  sequence_number: number;
  table_number: number | null;
  scheduled_at: string | null;
  duration_minutes: number;
  status: string;
  bracket: string | null;
  version: number;
  participants: Array<{ id: string; team_id: string | null; position: number; side: string | null }>;
}

export interface RankingEntry {
  rank: number;
  event_id: string;
  team_id: string;
  seed_score: number;
  best_score: number;
  average_score: number;
  rounds_played: number;
  updated_at: string;
}

export interface ScoringField {
  key: string;
  label: string;
  type: "count" | "number" | "boolean";
  multiplier: number;
  min_value: number | null;
  max_value: number | null;
  required: boolean;
  section?: string | null;
}

export interface ScoringSchema {
  id: string;
  season_id: string;
  event_id: string | null;
  competition_level_id: string | null;
  fields: ScoringField[];
  version: number;
  is_active: boolean;
}
