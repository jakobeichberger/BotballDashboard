/**
 * API errors → a message in the active UI language.
 *
 * The backend answers every error with `{ code, message, fieldErrors }`
 * (backend/main.py); `message` is English. Order of resolution:
 *   1. a specific `code` (validation_error, rate_limit_exceeded, …),
 *   2. a known backend message (errors.messages.<slug>, like a gettext msgid),
 *   3. in English, the backend message itself — it is specific and already
 *      in the right language,
 *   4. the HTTP status (errors.status.<status>), then the caller's fallback.
 * Client-side failures (offline, timeout, network) have their own texts.
 */
import i18n, { currentLanguage } from "@/i18n/config";
import { localizePolicyMessage } from "@/lib/passwordPolicy";

interface ApiErrorBody {
  code?: unknown;
  message?: unknown;
  detail?: unknown;
  fieldErrors?: Record<string, string[]>;
}

interface ErrorLike {
  code?: string;
  message?: string;
  response?: { status?: number; data?: ApiErrorBody };
}

const OFFLINE_WRITE_BLOCKED = "OFFLINE_WRITE_BLOCKED";

/** Stable key for a backend message: lower case, words joined by "_". */
export function messageSlug(message: string): string {
  return message
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80);
}

/** A known backend message in the active language, or null. */
export function localizeBackendMessage(message: string): string | null {
  // Password-policy rejections, also sent as field errors of password forms.
  const policy = localizePolicyMessage(message);
  if (policy !== message) return policy;
  const key = `common:errors.messages.${messageSlug(message)}`;
  return i18n.exists(key) ? i18n.t(key) : null;
}

function isErrorLike(value: unknown): value is ErrorLike {
  return typeof value === "object" && value !== null;
}

/** HTTP status of an API error, if the server answered. */
export function errorStatus(error: unknown): number | undefined {
  return isErrorLike(error) ? error.response?.status : undefined;
}

/** True when the request never got an answer (offline, timeout, DNS, …). */
export function isNetworkError(error: unknown): boolean {
  return isErrorLike(error) && !error.response && (error.code === "ERR_NETWORK" || error.code === "ECONNABORTED" || error.code === "ETIMEDOUT" || error.message === "Network Error");
}

function fieldErrorText(fieldErrors: Record<string, string[]> | undefined): string | null {
  if (!fieldErrors) return null;
  const messages = Object.values(fieldErrors).flat().filter((item) => typeof item === "string");
  if (!messages.length) return null;
  const localized = messages.map((item) => localizeBackendMessage(item));
  // Only field errors we can translate are shown one by one; otherwise the
  // generic validation text with the field names.
  if (localized.every(Boolean)) return localized.join(" ");
  if (currentLanguage() === "en") return messages.join(" ");
  return null;
}

/**
 * Message for the user. `fallback` is used when nothing more specific is known
 * (e.g. "Saving failed.").
 */
export function apiErrorMessage(error: unknown, fallback?: string): string {
  const generic = fallback ?? i18n.t("common:errors.generic");
  if (!isErrorLike(error)) return generic;
  if (error.message === OFFLINE_WRITE_BLOCKED) return i18n.t("common:errors.code.offline_write_blocked");
  if (!error.response) {
    if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") return i18n.t("common:errors.code.timeout");
    if (error.code === "ERR_CANCELED") return generic;
    if (isNetworkError(error) || (typeof navigator !== "undefined" && !navigator.onLine)) return i18n.t("common:errors.code.network");
    return generic;
  }
  const { status, data } = error.response;
  const code = typeof data?.code === "string" ? data.code : "";
  if (code === "validation_error" || Object.keys(data?.fieldErrors ?? {}).length > 0) {
    return fieldErrorText(data?.fieldErrors) ?? i18n.t("common:errors.code.validation_error", { fields: Object.keys(data?.fieldErrors ?? {}).join(", ") });
  }
  if (code && !code.startsWith("http_") && i18n.exists(`common:errors.code.${code}`)) return i18n.t(`common:errors.code.${code}`);
  const message = typeof data?.message === "string" ? data.message : typeof data?.detail === "string" ? data.detail : "";
  if (message) {
    const known = localizeBackendMessage(message);
    if (known) return known;
    if (currentLanguage() === "en") return message;
  }
  if (status && i18n.exists(`common:errors.status.${status}`)) return i18n.t(`common:errors.status.${status}`);
  if (status && status >= 500) return i18n.t("common:errors.status.500");
  return generic;
}
