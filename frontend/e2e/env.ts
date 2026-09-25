/**
 * Where the suite finds the app and which seeded logins it uses
 * (backend/scripts/seed_e2e.py creates them).
 */
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";

/**
 * The API as the browser reaches it. With VITE_API_URL set the app talks to
 * the backend directly (CI); otherwise it goes through the Vite proxy.
 */
export const API_URL = (process.env.E2E_API_URL ?? process.env.VITE_API_URL ?? `${BASE_URL}/api`).replace(/\/$/, "");

export const EVENT_SLUG = process.env.E2E_EVENT_SLUG ?? "e2e-event";

export const PASSWORD = process.env.E2E_PASSWORD ?? "test1234";

export type Role = "admin" | "juror" | "reviewer" | "mentor" | "mentor2" | "guest";

export const USERS: Record<Role, { email: string; password: string }> = Object.fromEntries(
  (["admin", "juror", "reviewer", "mentor", "mentor2", "guest"] as Role[]).map((role) => [
    role,
    { email: `${role}@test.local`, password: PASSWORD },
  ]),
) as Record<Role, { email: string; password: string }>;
