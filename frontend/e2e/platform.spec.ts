import { expect, test } from "@playwright/test";

const email = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const password = process.env.E2E_ADMIN_PASSWORD ?? "change-this-password";

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/e-mail|email/i).fill(email);
  await page.getByLabel(/passwort|password/i).fill(password);
  await page.getByRole("button", { name: /anmelden|sign in/i }).click();
  await expect(page).toHaveURL(/\/events\//);
});

test("admin can open setup and schedule", async ({ page }) => {
  await page.getByRole("link", { name: /event-verwaltung|event setup/i }).click();
  await expect(page.getByRole("heading", { name: /event-verwaltung/i })).toBeVisible();
  await page.getByRole("link", { name: /zeitplan|schedule/i }).click();
  await expect(page.getByRole("heading", { name: /zeitplan/i })).toBeVisible();
});

test("juror flow exposes dynamic official scoring form", async ({ page }) => {
  await page.getByRole("link", { name: /wertung|scoring/i }).click();
  await expect(page.getByRole("heading", { name: /mobile wertung|mobile scoring/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /offiziell speichern|save officially/i })).toBeVisible();
});

test("public scoreboard has no internal sidebar", async ({ page, request }) => {
  void request;
  const slug = process.env.E2E_EVENT_SLUG;
  test.skip(!slug, "E2E_EVENT_SLUG is provided by the seeded E2E environment");
  await page.goto(`/public/${slug}`);
  await expect(page.getByText("Botball Live")).toBeVisible();
  await expect(page.getByRole("navigation", { name: /hauptnavigation|main navigation/i })).toHaveCount(0);
});

test("paper review and printing workspaces are reachable", async ({ page }) => {
  await page.getByRole("link", { name: /paper-review/i }).click();
  await expect(page.getByRole("heading", { name: /paper/i })).toBeVisible();
  await page.getByRole("link", { name: /3d-druck|3d printing/i }).click();
  await expect(page.getByRole("heading", { name: /3d-druck/i })).toBeVisible();
});
