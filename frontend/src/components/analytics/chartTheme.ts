/**
 * Shared chart colours. Two categorical slots (validated blue/orange pair of
 * the reference palette) plus recessive grid and axis ink; series identity is
 * always backed by a legend or a direct label, never colour alone.
 */
export const SERIES = {
  primary: "#2a78d6",
  secondary: "#eb6834",
  muted: "#9ca3af",
} as const;

export const GRID = "#e5e7eb";
export const AXIS_TICK = { fontSize: 11, fill: "#6b7280" } as const;

/** Sequential single-hue scale (blue) for heatmap cells, 0..1 → CSS colour. */
export function heatColor(ratio: number | null | undefined): string {
  if (ratio == null || !Number.isFinite(ratio)) return "transparent";
  const clamped = Math.max(0, Math.min(1, ratio));
  // Light → dark blue; alpha keeps it readable on light and dark surfaces.
  return `rgba(42, 120, 214, ${0.08 + clamped * 0.72})`;
}

/** Text colour that stays legible on a heatColor() cell. */
export function heatTextClass(ratio: number | null | undefined): string {
  return ratio != null && ratio > 0.6 ? "text-white" : "text-fg";
}

export const DEADLINE_DOT: Record<string, string> = {
  red: "bg-red-500",
  orange: "bg-orange-500",
  green: "bg-green-600",
  blue: "bg-blue-600",
  purple: "bg-purple-600",
  gray: "bg-gray-400",
};
