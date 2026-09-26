/**
 * Score-sheet calculation — a line-by-line mirror of backend/modules/scoring/sheet.py.
 *
 * The backend total is authoritative; this module only drives the live preview
 * in the entry forms. Both are tested against the same fixtures
 * (./__fixtures__/score-sheet-cases.json), so a change on one side needs the
 * same change on the other.
 *
 * Structured sheet: per side, each section's Σ value × multiplier is multiplied
 * by its area multipliers (checkbox → factor, count → value × factor + offset,
 * either-or → the best alternative; anything below 1 counts as ×1). A derived
 * multiplier (`source`) has no input: it is on when that field of the section
 * is at least 1 (2026 Lower Start Box "Drum ×2"). A sum multiplier
 * (`type: "sum"`) multiplies by the sum — or with `mode: "product"` the
 * product — of its `inputs` (AIRCER "Max Stack Height + # of Stacks").
 * `allow_below_one` lets a factor below 1 apply (AIRCER Restricted Area ×0.5);
 * `zero_means: "zero"` makes an entered 0 zero the area. The total
 * is the sum over sides ("Total A + B"). A flat field list is the special case
 * of sections without multipliers.
 */

export type SheetValue = number | boolean | string | null | undefined;
export type RawScores = Record<string, SheetValue>;

export interface SheetField {
  key: string;
  label: string;
  type?: "count" | "number" | "boolean";
  multiplier?: number;
  min_value?: number | null;
  max_value?: number | null;
  required?: boolean;
  section?: string | null;
  role?: "field" | "multiplier";
}

/** One counted value of a sum multiplier ("Max Stack Height"). */
export interface SheetSumInput {
  key: string;
  label: string;
  min_value?: number | null;
  max_value?: number | null;
}

export interface SheetMultiplier {
  key: string;
  label: string;
  type?: "boolean" | "count" | "number" | "sum";
  factor?: number;
  offset?: number;
  min_value?: number | null;
  max_value?: number | null;
  /** Field of the same section that switches this checkbox multiplier on (≥ 1). */
  source?: string | null;
  /** type "sum": the values that are added (or multiplied, mode "product"). */
  inputs?: SheetSumInput[] | null;
  mode?: "sum" | "product";
  /** A factor below 1 applies (a penalty such as ×0.5) instead of counting as ×1. */
  allow_below_one?: boolean;
  /** count/number/sum: an entered 0 is neutral (×1, default) or zeroes the area. */
  zero_means?: "neutral" | "zero";
}

export interface SheetEitherMultiplier {
  key: string;
  label: string;
  either: SheetMultiplier[];
}

export type SectionMultiplier = SheetMultiplier | SheetEitherMultiplier;

export interface SheetSection {
  key: string;
  label: string;
  fields: SheetField[];
  multipliers: SectionMultiplier[];
}

export interface SheetDefinition {
  sides: string[];
  sections: SheetSection[];
}

export interface SectionResult {
  key: string;
  label: string;
  subtotal: number;
  multiplier: number;
  total: number;
}

export interface SideResult {
  side: string | null;
  total: number;
  sections: SectionResult[];
}

/** One value the form must not submit, for a localized message (formatSheetIssue). */
export interface SheetIssue {
  code: "notNumeric" | "belowMin" | "aboveMax";
  /** Raw-score key ("A.fry_potato"). */
  key: string;
  /** Field label, with the side when the sheet has sides ("A · Fries"). */
  label: string;
  limit?: number;
}

export interface SheetResult {
  total: number;
  sides: SideResult[];
  /**
   * Values the form must not submit (non-numeric, below the minimum, above the
   * maximum) as English messages like the backend's; `issues` has them
   * structured for display.
   */
  errors: string[];
  issues: SheetIssue[];
}

export interface InputSpec extends SheetField {
  fieldKey: string;
  side: string | null;
  sectionKey: string;
  group: string | null;
}

export const SIDE_SEPARATOR = ".";

export const rawKey = (side: string | null | undefined, key: string) => (side ? `${side}${SIDE_SEPARATOR}${key}` : key);

export const isEither = (multiplier: SectionMultiplier): multiplier is SheetEitherMultiplier => "either" in multiplier;

export function isStructured(definition: unknown): definition is SheetDefinition {
  return !!definition && typeof definition === "object" && Array.isArray((definition as SheetDefinition).sections);
}

/** Mirrors sheet.from_flat_fields: one section per `section` label, no multipliers. */
export function fromFlatFields(fields: SheetField[]): SheetDefinition {
  const sections: SheetSection[] = [];
  const byLabel = new Map<string, SheetSection>();
  for (const field of fields) {
    const label = field.section || "";
    let section = byLabel.get(label);
    if (!section) {
      section = { key: `section_${sections.length + 1}`, label, fields: [], multipliers: [] };
      byLabel.set(label, section);
      sections.push(section);
    }
    section.fields.push(field);
  }
  return { sides: [], sections };
}

export function normalize(fields: SheetField[] | null | undefined, definition: unknown): SheetDefinition | null {
  if (isStructured(definition)) return definition;
  if (fields && fields.length) return fromFlatFields(fields);
  return null;
}

export const isDerived = (multiplier: SheetMultiplier): boolean => !!multiplier.source;

export const isSum = (multiplier: SectionMultiplier): boolean => !isEither(multiplier) && multiplier.type === "sum";

const multiplierInputs = (multiplier: SectionMultiplier): SheetMultiplier[] => {
  if (isEither(multiplier)) return multiplier.either.filter((option) => !isDerived(option));
  if (multiplier.type === "sum") return (multiplier.inputs ?? []).map((item) => ({ ...item, type: "count", factor: 1 }));
  return isDerived(multiplier) ? [] : [multiplier];
};

/** Every value the sheet asks for, keyed like the raw scores the API expects. */
export function inputFields(definition: SheetDefinition): InputSpec[] {
  const out: InputSpec[] = [];
  const sides = definition.sides.length ? definition.sides : [null];
  for (const side of sides) {
    for (const section of definition.sections) {
      const sectionLabel = section.label || section.key;
      for (const field of section.fields) {
        out.push({ ...field, key: rawKey(side, field.key), fieldKey: field.key, side, section: sectionLabel, sectionKey: section.key, role: "field", group: null, type: field.type ?? "count", multiplier: field.multiplier ?? 1 });
      }
      for (const multiplier of section.multipliers) {
        for (const option of multiplierInputs(multiplier)) {
          out.push({ key: rawKey(side, option.key), fieldKey: option.key, label: option.label, side, section: sectionLabel, sectionKey: section.key, role: "multiplier", group: isEither(multiplier) || isSum(multiplier) ? multiplier.key : null, type: (option.type ?? "boolean") as SheetField["type"], multiplier: option.factor ?? 1, min_value: option.min_value ?? null, max_value: option.max_value ?? null });
        }
      }
    }
  }
  return out;
}

const round = (value: number, digits: number) => {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
};

class SheetError extends Error {}

function toNumber(key: string, value: SheetValue): number {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (value === null || value === undefined || value === "") return 0;
  const number = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(number)) throw new SheetError(`Score for '${key}' must be a number`);
  return number;
}

function readValue(raw: RawScores, key: string, spec: { max_value?: number | null }): number {
  const number = toNumber(key, raw[key]);
  if (spec.max_value !== null && spec.max_value !== undefined && number > spec.max_value) {
    throw new SheetError(`Score for '${key}' exceeds the maximum of ${spec.max_value}`);
  }
  return number;
}

/** Below 1 counts as neutral (×1) unless the multiplier allows a penalty. */
const applied = (factor: number, spec: SheetMultiplier) => (factor >= 1 ? factor : spec.allow_below_one ? Math.max(factor, 0) : 1);

function effective(raw: RawScores, side: string | null, spec: SheetMultiplier): number {
  if (spec.source) {
    const trigger = rawKey(side, spec.source);
    return toNumber(trigger, raw[trigger]) >= 1 ? applied(spec.factor ?? 1, spec) : 1;
  }
  const kind = spec.type ?? "boolean";
  if (kind === "boolean") return readValue(raw, rawKey(side, spec.key), spec) ? applied(spec.factor ?? 1, spec) : 1;
  let value: number;
  if (kind === "sum") {
    const values = (spec.inputs ?? []).map((item) => readValue(raw, rawKey(side, item.key), item));
    value = (spec.mode ?? "sum") === "product" ? values.reduce((product, item) => product * item, 1) : values.reduce((sum, item) => sum + item, 0);
  } else {
    value = readValue(raw, rawKey(side, spec.key), spec);
  }
  const factor = value * (spec.factor ?? 1) + (spec.offset ?? 0);
  // An empty box zeroes the area only when the definition says so, and never works as a penalty.
  if (value === 0) return (spec.zero_means ?? "neutral") === "zero" ? 0 : factor >= 1 ? factor : 1;
  return applied(factor, spec);
}

export function multiplierFactor(raw: RawScores, side: string | null, multiplier: SectionMultiplier): number {
  if (isEither(multiplier)) {
    // Like Python's max(..., default=1): the best alternative, ×1 without any.
    return multiplier.either.length ? Math.max(...multiplier.either.map((option) => effective(raw, side, option))) : 1;
  }
  return effective(raw, side, multiplier);
}

function computeStrict(raw: RawScores, definition: SheetDefinition | null): Omit<SheetResult, "errors" | "issues"> {
  if (!definition) {
    const total = Object.entries(raw).reduce((sum, [key, value]) => sum + toNumber(key, value), 0);
    return { total: round(total, 2), sides: [] };
  }
  let grandTotal = 0;
  const sides: SideResult[] = [];
  for (const side of definition.sides.length ? definition.sides : [null]) {
    let sideTotal = 0;
    const sections: SectionResult[] = [];
    for (const section of definition.sections) {
      let subtotal = 0;
      for (const field of section.fields) subtotal += readValue(raw, rawKey(side, field.key), field) * (field.multiplier ?? 1);
      let factor = 1;
      for (const multiplier of section.multipliers) factor *= multiplierFactor(raw, side, multiplier);
      const sectionTotal = subtotal * factor;
      sideTotal += sectionTotal;
      sections.push({ key: section.key, label: section.label, subtotal: round(subtotal, 2), multiplier: round(factor, 4), total: round(sectionTotal, 2) });
    }
    grandTotal += sideTotal;
    sides.push({ side, total: round(sideTotal, 2), sections });
  }
  return { total: round(grandTotal, 2), sides };
}

const ISSUE_MESSAGES: Record<SheetIssue["code"], (issue: SheetIssue) => string> = {
  notNumeric: (issue) => `${issue.key} must be numeric`,
  belowMin: (issue) => `${issue.key} must be at least ${issue.limit}`,
  aboveMax: (issue) => `${issue.key} must be at most ${issue.limit}`,
};

/**
 * What the entry form must not submit: non-numeric values, values above the
 * maximum and values below the minimum. A count without a configured minimum
 * cannot be negative (its input says min 0; the backend checks only a
 * configured minimum, so -3 reached it and failed as a generic error).
 * Missing required values are left to the backend.
 */
export function sheetIssues(raw: RawScores, definition: SheetDefinition | null): SheetIssue[] {
  const issues: SheetIssue[] = [];
  const specs = definition ? new Map(inputFields(definition).map((spec) => [spec.key, spec])) : new Map<string, InputSpec>();
  for (const [key, value] of Object.entries(raw)) {
    const spec = specs.get(key);
    if (definition && !spec) continue;
    const label = spec ? (spec.side ? `${spec.side} · ${spec.label}` : spec.label) : key;
    let number: number;
    try {
      number = toNumber(key, value);
    } catch {
      issues.push({ code: "notNumeric", key, label });
      continue;
    }
    if (!spec) continue;
    const min = spec.min_value ?? (spec.type === "count" ? 0 : null);
    if (min !== null && number < min) issues.push({ code: "belowMin", key, label, limit: min });
    if (spec.max_value !== null && spec.max_value !== undefined && number > spec.max_value) issues.push({ code: "aboveMax", key, label, limit: spec.max_value });
  }
  return issues;
}

/**
 * Total and breakdown. Where the backend raises (bad value, above maximum)
 * this reports the problem in `errors` / `issues` and previews the total with
 * that value clamped, so the form keeps showing a number while typing.
 */
export function computeSheet(raw: RawScores, definition: SheetDefinition | null): SheetResult {
  const issues = sheetIssues(raw, definition);
  const errors = issues.map((issue) => ISSUE_MESSAGES[issue.code](issue));
  try {
    return { ...computeStrict(raw, definition), errors, issues };
  } catch (error) {
    if (!(error instanceof SheetError)) throw error;
    const specs = definition ? new Map(inputFields(definition).map((spec) => [spec.key, spec])) : new Map<string, InputSpec>();
    const clamped: RawScores = {};
    for (const [key, value] of Object.entries(raw)) {
      const number = Number(typeof value === "boolean" ? Number(value) : value);
      const max = specs.get(key)?.max_value;
      clamped[key] = Number.isNaN(number) ? 0 : max !== null && max !== undefined ? Math.min(number, max) : number;
    }
    return { ...computeStrict(clamped, definition), errors: errors.length ? errors : [error.message], issues };
  }
}

export function computeTotal(raw: RawScores, fields: SheetField[] | null | undefined, definition?: unknown): number {
  return computeStrict(raw, normalize(fields, definition)).total;
}

/** Mirrors sheet.validate (the check the API runs before saving). */
export function validate(raw: RawScores, definition: SheetDefinition | null, options: { unknownKeys?: boolean } = {}): string[] {
  const errors: string[] = [];
  if (!definition) {
    for (const [key, value] of Object.entries(raw)) {
      try { toNumber(key, value); } catch { errors.push(`${key} must be numeric`); }
    }
    return errors;
  }
  const specs = new Map(inputFields(definition).map((spec) => [spec.key, spec]));
  for (const [key, spec] of specs) if (spec.required && !(key in raw)) errors.push(`${key} is required`);
  for (const [key, value] of Object.entries(raw)) {
    const spec = specs.get(key);
    if (!spec) {
      if (options.unknownKeys !== false) errors.push(`${key} is not part of the active scoring schema`);
      continue;
    }
    let number: number;
    try { number = toNumber(key, value); } catch { errors.push(`${key} must be numeric`); continue; }
    if (spec.min_value !== null && spec.min_value !== undefined && number < spec.min_value) errors.push(`${key} must be at least ${spec.min_value}`);
    if (spec.max_value !== null && spec.max_value !== undefined && number > spec.max_value) errors.push(`${key} must be at most ${spec.max_value}`);
  }
  return errors;
}
