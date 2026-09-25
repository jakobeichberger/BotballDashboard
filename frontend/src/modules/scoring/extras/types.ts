/**
 * Local types for the scoring-extras endpoints (backend/modules/scoring/extras_*).
 * Hand-written until the OpenAPI client is regenerated.
 */
import type { SheetDefinition } from "@/modules/scoring/sheet/calculator";

export interface TiebreakerCriterion {
  key: string;
  label: string;
  direction: "max" | "min";
  source: "sheet" | "entry";
  sheet_keys: string[];
  replay_only: boolean;
}

export interface ChecklistItem {
  /** The rule text (game review wording), shown under the label. */
  description?: string | null;
  key: string;
  label: string;
  required: boolean;
}

export interface RuleSet {
  season_id: string;
  tiebreakers: TiebreakerCriterion[];
  finals_replay: boolean;
  end_contact_bonus_percent: number;
  referee_checklist: ChecklistItem[];
  /** Off: equal seed scores share a rank (game review, ECER 2026). */
  seeding_tiebreakers?: boolean;
  /** Rubric maxima of the documentation periods (2026: 100 / 95 / 100 / 100). */
  doc_max_points?: DocMaxPoints;
}

export interface DocMaxPoints { p1: number; p2: number; p3: number; onsite: number }

export interface ChecklistPreset {
  id: string;
  name: string;
  items: ChecklistItem[];
}

export interface TiebreakerPreset {
  id: string;
  name: string;
  finals_replay: boolean;
  tiebreakers: TiebreakerCriterion[];
}

export interface SchemaTemplate {
  id: string;
  name: string;
  year: number;
  complete: boolean;
  source: string;
  notes: string;
  definition: SheetDefinition;
}

export interface SchemaListEntry {
  id: string;
  season_id: string;
  season_name: string | null;
  event_id: string | null;
  event_name: string | null;
  competition_level_id: string | null;
  competition_level_name: string | null;
  version: number;
  structured: boolean;
  field_count: number;
}

export interface HeadToHeadOutcome {
  scheduled_match_id: string;
  winner: string | null;
  reason: "disqualified" | "round_lost" | "score" | "tiebreaker" | "finals_replay" | "replay" | "incomplete";
  decided_by: string | null;
  replay: boolean;
  sides: Array<{
    match_id: string;
    team_id: string;
    team_name: string | null;
    sheet_score: number;
    bonus_score: number;
    total_score: number;
    is_disqualified: boolean;
    round_lost: boolean;
    round_lost_reason: string | null;
    end_contact: boolean;
  }>;
}

export interface DEPlacementEntry {
  bracket: string;
  team_id: string;
  team_name: string | null;
  de_rank: number | null;
  placement: number;
  decided_by: string | null;
}

export interface PartsChallenge {
  id: string;
  event_id: string;
  scheduled_match_id: string | null;
  challenger_team_id: string;
  challenged_team_id: string;
  description: string;
  /** null while open; true = upheld (challenged team DQ'd), false = rejected (challenger DQ'd). */
  upheld: boolean | null;
  ruling_note: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface ExternalTeam {
  id: string;
  season_id: string;
  name: string;
  number: string | null;
  country: string | null;
  school: string | null;
  source: "observed" | "official";
  notes: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface ScoutingNote {
  id: string;
  event_id: string;
  external_team_id: string;
  owner_team_id: string | null;
  author_id: string | null;
  body: string;
  threat_level: number | null;
  created_at: string;
  updated_at: string;
}

export interface ScoutingObservation {
  id: string;
  event_id: string;
  external_team_id: string;
  owner_team_id: string | null;
  phase: string;
  round_number: number | null;
  score: number;
  notes: string | null;
  created_at: string;
}

export interface OpponentRankingEntry {
  rank: number;
  kind: "internal" | "external";
  team_id: string;
  team_name: string;
  team_number: string | null;
  country: string | null;
  seed_score: number;
  best_score: number;
  runs: number;
  official_rank: number | null;
}

export interface CompetitionLevel {
  id: string;
  name: string;
  code: string;
  description: string | null;
  is_active: boolean;
  order: number;
  qualifies_from_level_id: string | null;
}

export interface QualificationStatusEntry {
  team_id: string;
  team_name: string;
  qualified: boolean;
  qualification_id: string | null;
  note: string | null;
}

export const LOSE_ROUND_REASONS = ["never_left_start_box", "motors_running", "other"] as const;
export type LoseRoundReason = (typeof LOSE_ROUND_REASONS)[number];
