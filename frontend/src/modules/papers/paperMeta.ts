// Shared paper-review vocabulary: status labels, review criteria and the local
// API shapes added with migration 0023 (not yet in the generated client).

export const PAPER_STATUS_BADGE: Record<string, string> = {
  draft: "badge-gray",
  submitted: "badge-blue",
  under_review: "badge-yellow",
  revision_requested: "badge-yellow",
  resubmitted: "badge-blue",
  accepted: "badge-green",
  rejected: "badge-red",
  disqualified_ai: "badge-red",
};

export const PAPER_STATUS_LABEL: Record<string, string> = {
  draft: "Entwurf",
  submitted: "Eingereicht",
  under_review: "In Prüfung",
  revision_requested: "Überarbeitung",
  resubmitted: "Neu eingereicht",
  accepted: "Angenommen",
  rejected: "Abgelehnt",
  disqualified_ai: "Disqualifiziert (KI)",
};

/** Statuses an organizer can set by hand. */
export const ADMIN_STATUS_OPTIONS = [
  "submitted",
  "under_review",
  "revision_requested",
  "accepted",
  "rejected",
  "disqualified_ai",
];

/** Statuses in which the team may upload a new version and (re)submit. */
export const EDITABLE_STATUSES = new Set(["draft", "revision_requested"]);
/** Statuses that still need reviewer attention. */
export const OPEN_REVIEW_STATUSES = new Set(["submitted", "resubmitted", "under_review"]);

export const RECOMMENDATION_LABEL: Record<string, string> = {
  accept: "Annehmen",
  revision_minor: "Kleine Überarbeitung",
  revision_major: "Große Überarbeitung",
  reject: "Ablehnen",
};
export const RECOMMENDATION_BADGE: Record<string, string> = {
  accept: "badge-green",
  revision_minor: "badge-yellow",
  revision_major: "badge-yellow",
  reject: "badge-red",
};

export type CriterionKey = "content" | "implementation" | "results" | "language" | "format";

/** The five criteria of the spec (module 06), each scored 0–10 with a comment. */
export const REVIEW_CRITERIA: { key: CriterionKey; label: string; hint: string }[] = [
  { key: "content", label: "Inhalt", hint: "Concept / Design" },
  { key: "implementation", label: "Technische Umsetzung", hint: "Implementation" },
  { key: "results", label: "Ergebnisse", hint: "Results / Conclusion" },
  { key: "language", label: "Sprache", hint: "Sprachliche Qualität" },
  { key: "format", label: "Formales", hint: "IEEE-Format, max. 5 Seiten" },
];

type CriterionScores = { [K in CriterionKey as `score_${K}`]: number | null };
type CriterionComments = { [K in CriterionKey as `comment_${K}`]: string | null };

export interface ReviewFeedback extends CriterionScores, CriterionComments {
  id: string;
  revision_number: number;
  version_number: number | null;
  total_score: number | null;
  comments: string | null;
  revision_notes: string | null;
  recommendation: string | null;
  submitted_at: string | null;
}

export interface PaperReview extends ReviewFeedback {
  paper_id: string;
  reviewer_id: string;
  private_notes: string | null;
  is_submitted: boolean;
  created_at: string;
}

export interface ReviewerAssignment {
  id: string;
  reviewer_id: string;
  assigned_at: string;
  due_at: string | null;
  status: string;
  version_number: number | null;
  reminder_sent_at: string | null;
  completed_at: string | null;
}

export interface PaperVersion {
  id: string;
  version_number: number;
  revision_number: number;
  file_name: string;
  file_size_bytes: number;
  uploaded_by: string | null;
  uploaded_at: string;
  submitted_at: string | null;
}

export interface PaperDeadline {
  deadline_date: string | null;
  timezone: string;
  cutoff_at: string | null;
  passed: boolean;
  locked: boolean;
  can_override: boolean;
}

export interface PaperDetail {
  id: string;
  season_id: string;
  event_id: string | null;
  team_id: string;
  title: string;
  abstract: string | null;
  competition_level_id: string | null;
  status: string;
  file_name: string | null;
  file_size_bytes: number | null;
  submitted_at: string | null;
  revision_number: number;
  current_version: number | null;
  final_score: number | null;
  paper_rank: number | null;
  format_deduction: number;
  format_deduction_reason: string | null;
  finalized_at: string | null;
  reviews: PaperReview[];
  assignments: ReviewerAssignment[];
  versions: PaperVersion[];
  feedback: ReviewFeedback[];
  deadline: PaperDeadline | null;
}

export interface PaperStats {
  total: number;
  by_status: Record<string, number>;
  decided: number;
  accepted: number;
  rejected: number;
  disqualified: number;
  acceptance_rate: number | null;
  average_final_score: number | null;
  average_review_score: number | null;
  criterion_averages: Record<CriterionKey, number | null>;
  reviews_submitted: number;
  reviews_open: number;
  average_revision_rounds: number | null;
}

/**
 * Human-readable time left until `cutoff` ("3 T 4 Std", "5 Std 12 Min",
 * "12 Min"), or null once it has passed.
 */
export function formatCountdown(cutoff: string | Date, now: Date = new Date()): string | null {
  const ms = new Date(cutoff).getTime() - now.getTime();
  if (ms <= 0) return null;
  const minutes = Math.floor(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `${days} T ${hours} Std`;
  if (hours > 0) return `${hours} Std ${mins} Min`;
  return `${Math.max(mins, 1)} Min`;
}

/** Axios error → message for the user (the API returns `message`, FastAPI `detail`). */
export function apiErrorMessage(error: unknown, fallback = "Aktion fehlgeschlagen."): string {
  const data = (error as { response?: { data?: { message?: string; detail?: unknown } } })
    ?.response?.data;
  if (typeof data?.message === "string") return data.message;
  if (typeof data?.detail === "string") return data.detail;
  return fallback;
}
