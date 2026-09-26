/**
 * Shared chart colours. Two categorical slots (brand signal red and a blue
 * that stays distinguishable from it for colour-blind viewers) plus recessive
 * grid and axis ink from the theme tokens (src/index.css), so charts follow
 * light and dark mode; series identity is always backed by a legend or a
 * direct label, never colour alone.
 */
export const SERIES = {
  primary: "rgb(var(--rot-rgb))",
  secondary: "rgb(var(--info))",
  muted: "rgb(var(--text-leise))",
} as const;

export const GRID = "rgb(var(--rand))";
export const AXIS_TICK = { fontSize: 11, fill: "rgb(var(--text-leise))" } as const;

/**
 * Legend order = the order of the series (dataKeys) as drawn; Recharts 3
 * sorts legend items alphabetically by default.
 */
export function legendOrder(...dataKeys: string[]) {
  return (item: { dataKey?: unknown }) => dataKeys.indexOf(String(item.dataKey));
}

/** Sequential single-hue scale (signal red) for heatmap cells, 0..1 → CSS colour. */
export function heatColor(ratio: number | null | undefined): string {
  if (ratio == null || !Number.isFinite(ratio)) return "transparent";
  const clamped = Math.max(0, Math.min(1, ratio));
  // Light → strong red; alpha keeps it readable on light and dark surfaces.
  return `rgb(var(--rot-rgb) / ${0.06 + clamped * 0.62})`;
}

/**
 * Text colour that stays legible on a heatColor() cell: the theme's text
 * colour keeps 4.5:1 on every step (dark ink on light red, white on red over
 * the dark surface).
 */
export function heatTextClass(_ratio?: number | null): string {
  return "text-fg";
}

export const DEADLINE_DOT: Record<string, string> = {
  red: "bg-red-500",
  orange: "bg-orange-500",
  green: "bg-green-600",
  blue: "bg-primary",
  purple: "bg-purple-600",
  gray: "bg-gray-400",
};
