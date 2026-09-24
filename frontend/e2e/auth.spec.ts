import { test, expect } from "@playwright/test";
import { login, USERS } from "./helpers";

/** The sidebar; "Einstellungen" also appears as an admin dashboard tile. */
const nav = (page: import("@playwright/test").Page) => page.getByLabel("Hauptnavigation");

test.describe("authentication", () => {
  test("admin can log in and reach the dashboard", async ({ page }) => {
    await login(page, USERS.admin);
    await expect(nav(page).getByRole("link", { name: /einstellungen/i })).toBeVisible();
  });

  test("wrong credentials keep the user on the login page", async ({ page }) => {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(USERS.admin.email);
    await page.locator('input[type="password"]').fill("definitely-wrong");
    await page.getByRole("button", { name: /anmelden/i }).click();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.getByRole("link", { name: /^dashboard$/i })).toHaveCount(0);
  });

  test("a guest does not see the admin settings link", async ({ page }) => {
    await login(page, USERS.guest);
    await expect(nav(page).getByRole("link", { name: /einstellungen/i })).toHaveCount(0);
  });

  test("logging out returns to the login form", async ({ page }) => {
    await login(page, USERS.admin);
    await page.getByRole("button", { name: /abmelden/i }).click();
    await expect(page.getByRole("button", { name: /anmelden/i })).toBeVisible();
  });
});
