import { describe, expect, it } from "vitest";
import { aerialMean, regionalDocScore } from "@/lib/scoring";
import parity from "./scoring-parity.json";

// The same cases are checked against the backend formulas
// (backend/tests/unit/test_scoring_parity.py), so the live preview can only
// drift from the stored score if one of the two tests fails.
describe("lib/scoring parity with the backend", () => {
  it.each(parity.documentation)("documentation score of $parts", ({ parts, score }) => {
    const result = regionalDocScore(parts);
    if (score === null) expect(result).toBeNull();
    else expect(result).toBeCloseTo(score, 9);
  });

  it.each(parity.aerial)("aerial mean of $runs", ({ runs, score }) => {
    const result = aerialMean(runs);
    if (score === null) expect(result).toBeNull();
    else expect(result).toBeCloseTo(score, 9);
  });
});
