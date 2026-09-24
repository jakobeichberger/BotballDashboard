// Mirrors backend/modules/auth/password_policy.py so forms can explain a
// rejected password before submitting. The backend check stays authoritative.
export const PASSWORD_MIN_LENGTH = 10;

export const PASSWORD_HINT = `Mindestens ${PASSWORD_MIN_LENGTH} Zeichen, nicht nur ein wiederholtes Zeichen und nicht die E-Mail-Adresse.`;

export function passwordProblem(password: string, email?: string | null): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Das Passwort muss mindestens ${PASSWORD_MIN_LENGTH} Zeichen lang sein.`;
  }
  if (new Set(password).size === 1) {
    return "Das Passwort darf nicht aus einem einzigen wiederholten Zeichen bestehen.";
  }
  if (email && password.trim().toLowerCase() === email.trim().toLowerCase()) {
    return "Das Passwort darf nicht der E-Mail-Adresse entsprechen.";
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
