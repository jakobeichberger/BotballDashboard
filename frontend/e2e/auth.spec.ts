import { expect, mainNav, openNav, test, USERS } from "./helpers";
import type { Page } from "@playwright/test";

const SETTINGS_LINK = /einstellungen|settings/i;

async function fillLoginForm(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel(/^e-?mail$/i).fill(email);
  // Exact name: a looser pattern would also match the "Passwort anzeigen" toggle.
  await page.getByLabel(/^(passwort|password)$/i).fill(password);
  await page.getByRole("button", { name: /^(anmelden|sign in)$/i }).click();
}

test.describe("authentication", () => {
  // The only tests that go through the form; everything else resumes a
  // stored session (see helpers.ts) to stay under the login rate limit.
  test("an admin signs in through the form and reaches the event dashboard", async ({ page }) => {
    await fillLoginForm(page, USERS.admin.email, USERS.admin.password);
    await expect(page).toHaveURL(/\/events\/[^/]+\/dashboard/);
    await expect(mainNav(page).getByRole("link", { name: SETTINGS_LINK })).toBeVisible();
  });

  test("wrong credentials keep the user on the login page", async ({ page }) => {
    await fillLoginForm(page, USERS.admin.email, "definitely-wrong");
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
    await expect(mainNav(page)).toHaveCount(0);
  });

  test("a guest does not see the admin settings", async ({ page, sessions }) => {
    await sessions.signIn("guest");
    await expect(mainNav(page).getByRole("link", { name: /dashboard/i })).toBeVisible();
    await expect(mainNav(page).getByRole("link", { name: SETTINGS_LINK })).toHaveCount(0);
  });

  test("signing out ends the session", async ({ page, sessions }) => {
    await sessions.signIn("juror");
    // The session is revoked below; the next juror test signs in afresh.
    sessions.discard(page);
    await page.getByRole("button", { name: /^(abmelden|sign out)$/i }).click();
    await expect(page.getByRole("button", { name: /^(anmelden|sign in)$/i })).toBeVisible();
    // The refresh cookie is gone too: a reload does not restore the session.
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("the main navigation opens from the menu button on phones @mobile", async ({ page, sessions }) => {
    test.skip(!test.info().project.use.isMobile, "phone layout only");
    await sessions.signIn("guest");
    await openNav(page, /^dashboard$/i);
    await expect(page).toHaveURL(/\/dashboard$/);
  });
});
