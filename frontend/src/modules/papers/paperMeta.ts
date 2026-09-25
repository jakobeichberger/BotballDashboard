// Shared paper-review vocabulary: status labels, review criteria and the local
// API shapes added with migration 0023 (not yet in the generated client).
import i18n from "@/i18n/config";
import { labelMap, labelMapKeys } from "@/i18n/labels";

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

export const PAPER_STATUS_LABEL = labelMap("papers:status", [
  "draft",
  "submitted",
  "under_review",
  "revision_requested",
  "resubmitted",
  "accepted",
  "rejected",
  "disqualified_ai",
]);

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

export const RECOMMENDATION_LABEL = labelMap("papers:recommendation", ["accept", "revision_minor", "revision_major", "reject"]);
export const RECOMMENDATION_BADGE: Record<string, string> = {
  accept: "badge-green",
  revision_minor: "badge-yellow",
  revision_major: "badge-yellow",
  reject: "badge-red",
};

export type CriterionKey = "content" | "implementation" | "results" | "language" | "format";

/** The five criteria of the spec (module 06), each scored 0–10 with a comment. */
function criterion(key: CriterionKey): { key: CriterionKey; label: string; hint: string } {
  labelMapKeys.add(`papers:criterion.${key}.label`);
  labelMapKeys.add(`papers:criterion.${key}.hint`);
  return {
    key,
    get label() {
      return i18n.t(`papers:criterion.${key}.label`);
    },
    get hint() {
      return i18n.t(`papers:criterion.${key}.hint`);
    },
  };
}

/** The five criteria of the spec (module 06), labels in the active language. */
export const REVIEW_CRITERIA = (["content", "implementation", "results", "language", "format"] as const).map(criterion);

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

export interface PaperStatusChange {
  id: string;
  paper_id: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  changed_by: string | null;
  changed_at: string;
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
  /** Blocking official_final deadline for revised versions (migration 0029). */
  final_deadline_date?: string | null;
  final_cutoff_at?: string | null;
  final_locked?: boolean;
  /** Every official and internal deadline of the season, resolved to the event's timezone. */
  deadlines?: (PaperDeadlineRow & { cutoff_at: string; passed: boolean })[];
}

/** A configured paper deadline (GET /papers/deadlines). */
export interface PaperDeadlineRow {
  id: string;
  season_id?: string;
  deadline_type: string;
  due_date: string;
  label: string | null;
  is_hard_block: boolean;
}

export const DEADLINE_TYPE_LABEL = labelMap("papers:deadlineType", [
  "official_submission",
  "official_final",
  "internal_draft",
  "internal_review",
  "internal_revision",
  "internal_final",
]);
export const OFFICIAL_DEADLINE_TYPES = new Set(["official_submission", "official_final"]);

/** Internal deadlines that have passed: a warning, never a lock. */
export function passedInternalDeadlines(deadline?: PaperDeadline | null) {
  return (deadline?.deadlines ?? []).filter((d) => d.passed && !OFFICIAL_DEADLINE_TYPES.has(d.deadline_type));
}

export interface PaperVersionMeta {
  version_number: number;
  file_name: string;
  file_size_bytes: number;
  uploaded_at: string;
  pages: number | null;
}

export interface PaperVersionDiff {
  from_version: PaperVersionMeta;
  to_version: PaperVersionMeta;
  text_available: boolean;
  reason: string | null;
  diff: string[];
  added: number;
  removed: number;
  truncated: boolean;
}

export interface AutoAssignResult {
  dry_run: boolean;
  assignments: { paper_id: string; paper_title: string; reviewer_id: string; reviewer_name: string }[];
  unfilled: { paper_id: string; paper_title: string; missing: number }[];
}

/** CSS class of one unified-diff line. */
export function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-gray-500";
  if (line.startsWith("@@")) return "text-blue-600 dark:text-blue-400";
  if (line.startsWith("+")) return "bg-green-50 text-green-800 dark:bg-green-900/30 dark:text-green-200";
  if (line.startsWith("-")) return "bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-200";
  return "text-gray-600 dark:text-gray-400";
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
 * "12 Min" / "3 d 4 h", …), or null once it has passed.
 */
export function formatCountdown(cutoff: string | Date, now: Date = new Date()): string | null {
  const ms = new Date(cutoff).getTime() - now.getTime();
  if (ms <= 0) return null;
  const minutes = Math.floor(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return i18n.t("papers:countdown.days", { days, hours });
  if (hours > 0) return i18n.t("papers:countdown.hours", { hours, mins });
  return i18n.t("papers:countdown.minutes", { mins: Math.max(mins, 1) });
}

/** Axios error → message for the user in the active language (see lib/errors). */
export { apiErrorMessage } from "@/lib/errors";
