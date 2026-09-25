/**
 * Client-side mirrors of the backend's stored score rules, used for live
 * previews while typing. The values that count are computed by the backend
 * (with the category's formula set, e.g. the ECER 2026 normalisation).
 */

// 2025/2026 game review: DocScore = 2/10·P1% + 2/10·P2% + 2/10·P3% + 4/10·Onsite%.
const DOC_WEIGHTS = [0.2, 0.2, 0.2, 0.4];
const DEFAULT_MAXIMA = [100, 100, 100, 100];

/**
 * Weighted documentation score 0–1; each part relative to its rubric maximum
 * (2026: 100 / 95 / 100 / 100), a missing part counts 0. Null when nothing is entered.
 */
export function regionalDocScore(parts: (number | null | undefined)[], maxima: readonly number[] = DEFAULT_MAXIMA): number | null {
  if (parts.every((p) => p == null)) return null;
  return parts.reduce<number>((sum, p, i) => sum + DOC_WEIGHTS[i] * ((p ?? 0) / (maxima[i] || 100)), 0);
}

/**
 * Aerial score: mean of the best `counted` runs (Aerial 2026: best three), or
 * of every recorded run when `counted` is not set (ECER 2025). Null without runs.
 */
export function aerialScore(runs: (number | null | undefined)[], counted?: number | null): number | null {
  const vals = runs.filter((v): v is number => v != null).sort((a, b) => b - a);
  const used = counted ? vals.slice(0, counted) : vals;
  if (used.length === 0) return null;
  return used.reduce((a, b) => a + b, 0) / used.length;
}

/** Mean of every recorded run (ECER 2025). */
export const aerialMean = (runs: (number | null | undefined)[]): number | null => aerialScore(runs);
