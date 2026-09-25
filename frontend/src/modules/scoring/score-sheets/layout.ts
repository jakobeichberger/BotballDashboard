/**
 * Geometry of OCR layout boxes and the OCR validation rules. Boxes are stored
 * normalized (0–1 of the page); older layouts may still hold pixel values.
 */
import type { OcrAnchor, OcrFieldRule, OcrRegion, OcrSumRule, OcrValidationRules } from './api/scoreSheets'

// A4 portrait at 300 dpi, the default when neither layout nor image says otherwise.
export const DEFAULT_PAGE = { width: 2480, height: 3508 }
// Smaller drags are treated as clicks, not as boxes.
export const MIN_SIZE = 0.005

const round = (value: number) => Math.round(value * 10000) / 10000
export const clamp01 = (value: number) => (Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0)

/** Regions as normalized boxes; pixel regions (any value > 1) are divided by the page size. */
export function normalizeRegions(regions: OcrRegion[] | null | undefined, pageWidth: number, pageHeight: number): OcrRegion[] {
  return (regions ?? []).map((region) => {
    const pixels = Math.max(region.x, region.y, region.width, region.height) > 1
    if (!pixels) return { ...region }
    return {
      key: region.key,
      x: round(region.x / pageWidth),
      y: round(region.y / pageHeight),
      width: round(region.width / pageWidth),
      height: round(region.height / pageHeight),
    }
  })
}

/** The box spanned by two normalized points, clipped to the page. */
export function rectFromPoints(key: string, a: { x: number; y: number }, b: { x: number; y: number }): OcrRegion {
  const x1 = clamp01(Math.min(a.x, b.x))
  const y1 = clamp01(Math.min(a.y, b.y))
  const x2 = clamp01(Math.max(a.x, b.x))
  const y2 = clamp01(Math.max(a.y, b.y))
  return { key, x: round(x1), y: round(y1), width: round(x2 - x1), height: round(y2 - y1) }
}

/** Keeps a box inside the page after a numeric edit. */
export function fitRegion(region: OcrRegion): OcrRegion {
  const x = clamp01(region.x)
  const y = clamp01(region.y)
  return {
    key: region.key,
    x: round(x),
    y: round(y),
    width: round(Math.min(Math.max(region.width, MIN_SIZE), 1 - x)),
    height: round(Math.min(Math.max(region.height, MIN_SIZE), 1 - y)),
  }
}

// Anchors share the box geometry; their "key" is the name.
const asRegion = ({ name, ...box }: OcrAnchor): OcrRegion => ({ key: name, ...box })
const asAnchor = ({ key, ...box }: OcrRegion): OcrAnchor => ({ name: key, ...box })

export function normalizeAnchors(anchors: OcrAnchor[] | null | undefined, pageWidth: number, pageHeight: number): OcrAnchor[] {
  return normalizeRegions((anchors ?? []).map(asRegion), pageWidth, pageHeight).map(asAnchor)
}

export const fitAnchor = (anchor: OcrAnchor): OcrAnchor => asAnchor(fitRegion(asRegion(anchor)))

/** First free "anchor_<n>" name. */
export function nextAnchorName(anchors: OcrAnchor[]): string {
  const names = new Set(anchors.map((anchor) => anchor.name))
  let index = anchors.length + 1
  while (names.has(`anchor_${index}`)) index += 1
  return `anchor_${index}`
}

// The worker needs two marks for shift/rotation/scale; four also undo perspective.
export const MIN_ANCHORS = 2
export const DEFAULT_MIN_CONFIDENCE = 0.85

const numberOrNull = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

/**
 * Stored rules as editable state. Rules for fields that no longer exist and
 * anything in an older shape are dropped, like the worker ignores them.
 */
export function parseRules(raw: unknown, fieldKeys: ReadonlySet<string>): OcrValidationRules {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const confidence = numberOrNull(source.min_confidence)
  const fields = (Array.isArray(source.fields) ? source.fields : [])
    .filter((rule): rule is Record<string, unknown> => !!rule && typeof rule === 'object' && fieldKeys.has(String((rule as Record<string, unknown>).key)))
    .map((rule): OcrFieldRule => ({
      key: String(rule.key),
      min_value: numberOrNull(rule.min_value),
      max_value: numberOrNull(rule.max_value),
      integer: rule.integer === true,
      min_confidence: numberOrNull(rule.min_confidence),
    }))
  const sums = (Array.isArray(source.sums) ? source.sums : [])
    .filter((rule): rule is Record<string, unknown> => !!rule && typeof rule === 'object')
    .map((rule): OcrSumRule => ({
      label: String(rule.label ?? ''),
      keys: (Array.isArray(rule.keys) ? rule.keys : []).map(String).filter((key) => fieldKeys.has(key)),
      min_value: numberOrNull(rule.min_value),
      max_value: numberOrNull(rule.max_value),
    }))
  return { min_confidence: confidence !== null && confidence >= 0 && confidence <= 1 ? confidence : DEFAULT_MIN_CONFIDENCE, fields, sums }
}

/** Drops field rules that check nothing, so the stored rules stay readable. */
export function compactRules(rules: OcrValidationRules): OcrValidationRules {
  return {
    ...rules,
    fields: rules.fields.filter((rule) => rule.min_value !== null || rule.max_value !== null || rule.integer || rule.min_confidence !== null),
  }
}

export type RulesProblem = 'fieldRange' | 'sumLabel' | 'sumFields' | 'sumBounds' | 'sumRange'

/** The first reason the backend would reject the rules, with the rule it concerns. */
export function rulesProblem(rules: OcrValidationRules): { problem: RulesProblem; name: string } | null {
  for (const rule of rules.fields) {
    if (rule.min_value !== null && rule.max_value !== null && rule.min_value > rule.max_value) return { problem: 'fieldRange', name: rule.key }
  }
  for (const [index, rule] of rules.sums.entries()) {
    const name = rule.label.trim() || String(index + 1)
    if (!rule.label.trim()) return { problem: 'sumLabel', name }
    if (rule.keys.length < 2) return { problem: 'sumFields', name }
    if (rule.min_value === null && rule.max_value === null) return { problem: 'sumBounds', name }
    if (rule.min_value !== null && rule.max_value !== null && rule.min_value > rule.max_value) return { problem: 'sumRange', name }
  }
  return null
}
