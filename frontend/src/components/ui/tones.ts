/**
 * Status tones of the portal style (stat cards, callouts): a coloured border
 * and a tinted icon square per tone. Text colours are the AA status tokens.
 */
export type Tone = "primary" | "success" | "warning" | "danger" | "info" | "neutral";

export const TONE_BORDER: Record<Tone, string> = {
  primary: "border-primary/70",
  success: "border-success/60",
  warning: "border-warning/60",
  danger: "border-danger/60",
  info: "border-info/50",
  neutral: "border-rand",
};

export const TONE_ICON: Record<Tone, string> = {
  primary: "bg-primary/10 text-akzent",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
  info: "bg-info/10 text-info",
  neutral: "bg-flaeche-2 text-leise",
};

/** Callout box (hint, warning, error) with the tone's border and tint. */
export const TONE_CALLOUT: Record<Tone, string> = {
  primary: "border-primary/40 bg-primary/6",
  success: "border-success/40 bg-success/[0.07]",
  warning: "border-warning/45 bg-warning/8",
  danger: "border-danger/40 bg-danger/[0.07]",
  info: "border-info/40 bg-info/[0.07]",
  neutral: "border-rand bg-flaeche-2",
};
