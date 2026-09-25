/**
 * Client-side mirrors of the backend's stored score rules, used for live
 * previews while typing. The values that count are computed by the backend.
 */

// 2025/2026 game review: DocScore = 2/10·P1 + 2/10·P2 + 2/10·P3 + 4/10·Onsite.
const DOC_WEIGHTS = [0.2, 0.2, 0.2, 0.4];

/** Weighted documentation score 0–1; a missing part counts 0. Null when nothing is entered. */
export function regionalDocScore(parts: (number | null | undefined)[]): number | null {
  if (parts.every((p) => p == null)) return null;
  return parts.reduce<number>((sum, p, i) => sum + DOC_WEIGHTS[i] * ((p ?? 0) / 100), 0);
}

/** Aerial score: mean of every recorded run (ECER 2025). Null without runs. */
export function aerialMean(runs: (number | null | undefined)[]): number | null {
  const vals = runs.filter((v): v is number => v != null);
  if (vals.length === 0) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}
