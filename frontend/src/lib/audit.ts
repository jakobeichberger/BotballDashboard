/** Helpers for the event audit trail (score and result revisions). */

export interface ScoreRevision {
  id: string;
  /** null once the match was deleted; match_ref keeps the original id. */
  match_id: string | null;
  match_ref: string | null;
  team_id: string | null;
  event_id: string;
  revision: number;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown>;
  reason: string | null;
  changed_by: string | null;
  created_at: string;
}

export interface ResultRevision {
  id: string;
  event_id: string;
  team_id: string;
  kind: "de" | "aerial" | "doc" | string;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  changed_by: string | null;
  created_at: string;
}

export interface FieldChange {
  /** Field name; raw score fields are prefixed with "raw_scores.". */
  key: string;
  before: unknown;
  after: unknown;
}

// Bookkeeping fields that say nothing about the result itself.
const IGNORED = new Set(["id", "event_id", "team_id", "season_id", "created_at", "updated_at", "version", "deleted"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

/**
 * The fields that differ between two revision snapshots. Nested objects
 * (raw_scores, tiebreak_values) are compared per entry, so a corrected sheet
 * shows "raw_scores.cubes: 3 → 5" instead of two whole objects.
 */
export function revisionChanges(previous: Record<string, unknown> | null | undefined, next: Record<string, unknown> | null | undefined): FieldChange[] {
  const before = previous ?? {};
  const after = next ?? {};
  const changes: FieldChange[] = [];
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter((key) => !IGNORED.has(key)).sort();
  for (const key of keys) {
    const a = before[key];
    const b = after[key];
    if (same(a, b)) continue;
    if (isRecord(a) || isRecord(b)) {
      const inner = revisionChanges(isRecord(a) ? a : {}, isRecord(b) ? b : {});
      changes.push(...inner.map((change) => ({ ...change, key: `${key}.${change.key}` })));
    } else {
      changes.push({ key, before: a, after: b });
    }
  }
  return changes;
}

export type ScoreRevisionKind = "created" | "deleted" | "updated";

export function scoreRevisionKind(revision: Pick<ScoreRevision, "previous_value" | "new_value">): ScoreRevisionKind {
  if (revision.new_value?.deleted) return "deleted";
  return revision.previous_value ? "updated" : "created";
}

/** Human-readable value of a snapshot entry ("—" for empty). */
export function formatAuditValue(value: unknown, yes: string, no: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? yes : no;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
