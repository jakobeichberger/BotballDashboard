// Mirrors backend/modules/auth/password_policy.py so forms can explain a
// rejected password before submitting. The backend check stays authoritative.
import i18n from "@/i18n/config";

export const PASSWORD_MIN_LENGTH = 10;

/** The password rules in the active language. */
export function passwordHint(): string {
  return i18n.t("auth:password.hint", { min: PASSWORD_MIN_LENGTH });
}

export function passwordProblem(password: string, email?: string | null): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return i18n.t("auth:password.tooShort", { min: PASSWORD_MIN_LENGTH });
  }
  if (new Set(password).size === 1) {
    return i18n.t("auth:password.repeated");
  }
  if (email && password.trim().toLowerCase() === email.trim().toLowerCase()) {
    return i18n.t("auth:password.isEmail");
  }
  return null;
}

/** Turn an API error into a readable message (FastAPI detail or validation errors). */
export function apiErrorMessage(error: any, fallback: string): string {
  const data = error?.response?.data;
  // Validation errors carry the useful text per field; the generic message
  // (which the API client also copies into `detail`) says little.
  if (data?.fieldErrors) {
    const messages = Object.values(data.fieldErrors as Record<string, string[]>).flat();
    if (messages.length) return messages.join(" ");
  }
  if (typeof data?.detail === "string") return data.detail;
  if (typeof data?.message === "string") return data.message;
  return fallback;
}
