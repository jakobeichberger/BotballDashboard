import { describe, expect, it } from "vitest";
import fixtures from "@/modules/scoring/sheet/__fixtures__/score-sheet-cases.json";
import { computeSheet, computeTotal, inputFields, normalize, validate, type RawScores, type SheetDefinition, type SheetField } from "@/modules/scoring/sheet/calculator";

// Same fixtures as backend/tests/unit/test_score_sheet_calc.py.
interface FixtureSchema { fields?: SheetField[]; definition?: SheetDefinition }
interface FixtureCase {
  name: string;
  schema: string;
  raw: RawScores;
  total?: number;
  error?: boolean;
  side_totals?: Record<string, number>;
  sections?: Record<string, [number, number, number]>;
}
const schemas = fixtures.schemas as unknown as Record<string, FixtureSchema>;
const cases = fixtures.cases as unknown as FixtureCase[];

describe("score-sheet calculator (shared fixtures)", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, testCase) => {
    const schema = schemas[testCase.schema];
    const definition = normalize(schema.fields, schema.definition);
    if (testCase.error) {
      expect(() => computeTotal(testCase.raw, schema.fields, schema.definition)).toThrow();
      expect(computeSheet(testCase.raw, definition).errors.length).toBeGreaterThan(0);
      return;
    }
    expect(computeTotal(testCase.raw, schema.fields, schema.definition)).toBe(testCase.total);
    const result = computeSheet(testCase.raw, definition);
    expect(result.errors).toEqual([]);
    expect(result.total).toBe(testCase.total);
    for (const [side, total] of Object.entries(testCase.side_totals ?? {})) {
      expect(result.sides.find((s) => s.side === side)?.total).toBe(total);
    }
    for (const [path, [subtotal, multiplier, total]] of Object.entries(testCase.sections ?? {})) {
      const dot = path.lastIndexOf(".");
      const side = dot >= 0 ? path.slice(0, dot) : null;
      const key = path.slice(dot + 1);
      const section = result.sides.find((s) => s.side === side)?.sections.find((s) => s.key === key);
      expect([section?.subtotal, section?.multiplier, section?.total], path).toEqual([subtotal, multiplier, total]);
    }
  });
});

describe("validation mirror", () => {
  const definition = schemas.botball_2025.definition as SheetDefinition;

  it("rejects keys outside the schema and values above the maximum", () => {
    expect(validate({ "A.fry_potato": 2 }, definition)).toEqual([]);
    expect(validate({ fry_potato: 1 }, definition)).toEqual(["fry_potato is not part of the active scoring schema"]);
    expect(validate({ "A.condiment_sorted_stations": 4 }, definition)).toEqual(["A.condiment_sorted_stations must be at most 3"]);
  });

  it("keeps previewing a clamped total while reporting the error", () => {
    const result = computeSheet({ "A.fry_potato": 5 }, definition);
    expect(result.total).toBe(100);
    expect(result.errors).toEqual(["A.fry_potato must be at most 2"]);
  });

  it("lists every input per side, either-or options included", () => {
    const keys = inputFields(definition).map((spec) => spec.key);
    expect(keys).toContain("B.beverage_six_bottles");
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("2026 sheet (derived multipliers)", () => {
  const definition = schemas.botball_2026.definition as SheetDefinition;

  it("has no input for a multiplier that follows a field", () => {
    const keys = inputFields(definition).map((spec) => spec.key);
    expect(keys).toContain("A.lower_start_box_drums");
    expect(keys).not.toContain("A.lower_start_box_drum_bonus");
    expect(validate({ "A.lower_start_box_drum_bonus": true }, definition)).toEqual(["A.lower_start_box_drum_bonus is not part of the active scoring schema"]);
  });

  it("switches the Lower Start Box bonus on with the drum count", () => {
    expect(computeSheet({ "A.lower_start_box_drums": 0, "A.lower_start_box_poms": 1 }, definition).total).toBe(2);
    expect(computeSheet({ "A.lower_start_box_drums": 1, "A.lower_start_box_poms": 1 }, definition).total).toBe(54);
  });
});

describe("entry issues (frontend review M4)", () => {
  const flat = normalize([{ key: "cubes", label: "Würfel", type: "count", multiplier: 3, max_value: 20 }, { key: "bonus", label: "Bonus", type: "number", multiplier: 1 }], null);

  it("reports a negative count although the schema sets no minimum", () => {
    const result = computeSheet({ cubes: -3 }, flat);
    expect(result.issues).toEqual([{ code: "belowMin", key: "cubes", label: "Würfel", limit: 0 }]);
    expect(result.errors).toEqual(["cubes must be at least 0"]);
    // A plain number field without a minimum may be negative.
    expect(computeSheet({ bonus: -3 }, flat).issues).toEqual([]);
  });

  it("names the field and its side, not the internal key", () => {
    const definition = fixtures.schemas.botball_2025.definition as unknown as SheetDefinition;
    const [issue] = computeSheet({ "A.fry_potato": 5 }, definition).issues;
    expect(issue).toMatchObject({ code: "aboveMax", key: "A.fry_potato", limit: 2 });
    expect(issue.label).toMatch(/^A · /);
    expect(issue.label).not.toContain("fry_potato");
  });
});
