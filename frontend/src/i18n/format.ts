/**
 * Locale-aware display formatting (Intl) for the active UI language.
 *
 * Components that call these helpers should also call `useTranslation()` so
 * they re-render when the language changes.
 */
import { currentLanguage } from "./config";

type DateInput = Date | string | number | null | undefined;

const LOCALES = { de: "de-AT", en: "en-GB" } as const;

/** BCP 47 locale for Intl of the active language. */
export function intlLocale(): string {
  return LOCALES[currentLanguage()];
}

function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === "") return null;
  // Plain dates ("2026-09-25") are calendar days, not UTC midnight.
  const date = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Date only, e.g. 25.09.2026 / 25/09/2026. Empty values render as the fallback. */
export function formatDate(value: DateInput, options?: Intl.DateTimeFormatOptions, fallback = "—"): string {
  const date = toDate(value);
  return date ? date.toLocaleDateString(intlLocale(), options) : fallback;
}

/** Date and time, e.g. 25.09.2026, 14:30. */
export function formatDateTime(value: DateInput, options?: Intl.DateTimeFormatOptions, fallback = "—"): string {
  const date = toDate(value);
  return date ? date.toLocaleString(intlLocale(), options) : fallback;
}

/** Time only, e.g. 14:30. */
export function formatTime(value: DateInput, options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" }, fallback = "—"): string {
  const date = toDate(value);
  return date ? date.toLocaleTimeString(intlLocale(), options) : fallback;
}

/** Scores are shown with two decimals, e.g. 123,50 / 123.50. */
export function formatScore(value: number | null | undefined, fallback = "—"): string {
  return formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 2 }, fallback);
}

/** Number with locale grouping/decimal separators. */
export function formatNumber(value: number | null | undefined, options?: Intl.NumberFormatOptions, fallback = "—"): string {
  return value === null || value === undefined || Number.isNaN(value) ? fallback : value.toLocaleString(intlLocale(), options);
}
