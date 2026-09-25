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

// The backend's policy messages (English) and their translation keys. The
// common-password list only exists on the server, so its rejection can only
// be explained after submitting.
const POLICY_MESSAGES: Array<[RegExp, string]> = [
  [/common or leaked passwords/i, "auth:password.common"],
  [/at least \d+ characters/i, "auth:password.tooShort"],
  [/single repeated character/i, "auth:password.repeated"],
  [/must not be the e-mail address/i, "auth:password.isEmail"],
];

/** A backend password-policy message in the active language; other messages unchanged. */
export function localizePolicyMessage(message: string): string {
  const match = POLICY_MESSAGES.find(([pattern]) => pattern.test(message));
  return match ? i18n.t(match[1], { min: PASSWORD_MIN_LENGTH }) : message;
}

// API errors in general: lib/errors (apiErrorMessage), which also localizes
// these policy messages.
