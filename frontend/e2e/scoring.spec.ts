import { test, expect } from "@playwright/test";
import { login, USERS } from "./helpers";

test.describe("score entry", () => {
  test("a mentor only sees their own team and submits for jury confirmation", async ({ page }) => {
    await login(page, USERS.mentor);
    await page.goto("/scoring/entry");

    await expect(page.getByRole("heading", { name: /wertung erfassen/i })).toBeVisible();
    await expect(page.getByText(/zur bestätigung durch die jury/i)).toBeVisible();

    // Scoped to their own team only.
    const teamSelect = page.getByRole("combobox").first();
    await expect(teamSelect.locator("option")).toHaveCount(2); // placeholder + RoboLions
    await expect(teamSelect.locator("option", { hasText: "RoboLions" })).toHaveCount(1);

    // Mentors may not confirm or delete — no action buttons.
    await expect(page.getByTitle("Bestätigen")).toHaveCount(0);
  });

  test("switching to Vorbereitung explains that practice runs are excluded", async ({ page }) => {
    await login(page, USERS.mentor);
    await page.goto("/scoring/entry");

    await page.getByRole("button", { name: /vorbereitung/i }).click();
    await expect(page.getByText(/zählen nicht zur offiziellen rangliste/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /übungslauf speichern/i })).toBeVisible();
  });

  test("a juror can confirm and sees every team", async ({ page }) => {
    await login(page, USERS.juror);
    await page.goto("/scoring/entry");
    const teamSelect = page.getByRole("combobox").first();
    // Placeholder + all six seeded teams.
    await expect(teamSelect.locator("option")).toHaveCount(7);
  });

  test("the scoreboard ranks the seeded teams", async ({ page }) => {
    await login(page, USERS.guest);
    await page.goto("/scoring");
    await expect(page.getByRole("heading", { name: /rangliste/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /robolions/i }).first()).toBeVisible();
  });
});
