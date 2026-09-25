/**
 * Geometry of OCR layout boxes. Boxes are stored normalized (0–1 of the page);
 * older layouts may still hold pixel values.
 */
import type { OcrRegion } from './api/scoreSheets'

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
