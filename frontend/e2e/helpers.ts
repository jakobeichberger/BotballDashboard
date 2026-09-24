import { Page, expect } from "@playwright/test";

/** Seeded dev logins (see the seed script / README). */
export const USERS = {
  admin: { email: "admin@test.local", password: "test1234" },
  juror: { email: "juror@test.local", password: "test1234" },
  reviewer: { email: "reviewer@test.local", password: "test1234" },
  mentor: { email: "mentor@test.local", password: "test1234" },
  guest: { email: "guest@test.local", password: "test1234" },
};

/** Log in through the real login form and wait until the shell is rendered. */
export async function login(page: Page, user: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByPlaceholder("admin@example.com").fill(user.email);
  await page.locator('input[type="password"]').fill(user.password);
  await page.getByRole("button", { name: /anmelden/i }).click();
  // The sidebar only renders once authenticated.
  await expect(page.getByRole("link", { name: /dashboard/i })).toBeVisible();
}

/**
 * App pages live under /events/:eventId/…. Resolve the event the app opens by
 * default (the live one, else the first) and navigate to `path` within it.
 */
export async function gotoInEvent(page: Page, path: string) {
  await page.goto("/");
  await page.waitForURL(/\/events\/[^/]+\//);
  const eventId = new URL(page.url()).pathname.split("/")[2];
  await page.goto(`/events/${eventId}${path}`);
}
