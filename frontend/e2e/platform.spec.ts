import { expect, test, type Page } from "@playwright/test";

const email = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const password = process.env.E2E_ADMIN_PASSWORD ?? "change-this-password";

/**
 * The sidebar. The admin dashboard repeats some destinations as quick links,
 * so unscoped link lookups would be ambiguous.
 */
const mainNav = (page: Page) =>
  page.getByRole("navigation", { name: /hauptnavigation|main navigation/i });

test("public scoreboard has no internal sidebar", async ({ page }) => {
  const slug = process.env.E2E_EVENT_SLUG;
  test.skip(!slug, "E2E_EVENT_SLUG is provided by the seeded E2E environment");
  // Anonymous on purpose: the public board must work without a session.
  await page.goto(`/public/${slug}`);
  await expect(page.getByText("Botball Live")).toBeVisible();
  await expect(mainNav(page)).toHaveCount(0);
});

// Login is rate limited (10 per minute per IP), so only tests that need a
// session log in, keeping even a run with CI retries under the limit.
test.describe("signed in as admin", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/e-mail|email/i).fill(email);
    // Exact name: a regex would also match the "Passwort anzeigen" toggle button.
    await page.getByRole("textbox", { name: /^(passwort|password)$/i }).fill(password);
    await page.getByRole("button", { name: /anmelden|sign in/i }).click();
    await expect(page).toHaveURL(/\/events\//);
  });

  test("admin can open setup and schedule", async ({ page }) => {
    await mainNav(page).getByRole("link", { name: /event-verwaltung|event setup/i }).click();
    await expect(page.getByRole("heading", { name: /event-verwaltung/i })).toBeVisible();
    await mainNav(page).getByRole("link", { name: /zeitplan|schedule/i }).click();
    await expect(page.getByRole("heading", { name: /zeitplan/i })).toBeVisible();
  });

  test("juror flow exposes dynamic official scoring form", async ({ page }) => {
    await mainNav(page).getByRole("link", { name: /wertung|scoring/i }).click();
    await expect(page.getByRole("heading", { name: /mobile wertung|mobile scoring/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /prüfen & absenden|review & submit/i })).toBeVisible();
  });

  test("paper review and printing workspaces are reachable", async ({ page }) => {
    await mainNav(page).getByRole("link", { name: /paper-review/i }).click();
    await expect(page.getByRole("heading", { name: /paper/i })).toBeVisible();
    await mainNav(page).getByRole("link", { name: /3d-druck|3d printing/i }).click();
    await expect(page.getByRole("heading", { name: /3d-druck/i })).toBeVisible();
  });
});
