import { describe, expect, it } from "vitest";
import { aerialMean, aerialScore, regionalDocScore } from "@/lib/scoring";
import parity from "./scoring-parity.json";

interface DocCase { parts: (number | null)[]; maxima?: number[]; score: number | null }
interface AerialCase { runs: (number | null)[]; counted?: number; score: number | null }

// The same cases are checked against the backend formulas
// (backend/tests/unit/test_scoring_parity.py), so the live preview can only
// drift from the stored score if one of the two tests fails.
describe("lib/scoring parity with the backend", () => {
  it.each(parity.documentation as DocCase[])("documentation score of $parts", ({ parts, maxima, score }) => {
    const result = regionalDocScore(parts, maxima);
    if (score === null) expect(result).toBeNull();
    else expect(result).toBeCloseTo(score, 9);
  });

  it.each(parity.aerial as AerialCase[])("aerial score of $runs", ({ runs, counted, score }) => {
    const result = aerialScore(runs, counted);
    if (score === null) expect(result).toBeNull();
    else expect(result).toBeCloseTo(score, 9);
  });

  it("aerialMean counts every run", () => {
    expect(aerialMean([70, 52.5, 115, 30, 60, 105])).toBeCloseTo(72.083333333, 6);
  });
});
