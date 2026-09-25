import { expect, gotoInEvent, test } from "./helpers";
import type { Page } from "@playwright/test";

/** The team picker of the score entry form (first select of the page body). */
const teamSelect = (page: Page) => page.getByRole("main").getByRole("combobox").first();

test.describe("score entry", () => {
  test("a mentor only sees their own team and submits for jury confirmation", async ({ page, sessions }) => {
    await sessions.signIn("mentor");
    await gotoInEvent(page, "/scoring/entry");

    await expect(page.getByRole("heading", { name: /wertung erfassen|enter score/i })).toBeVisible();
    await expect(page.getByText(/zur bestätigung durch die jury|confirmation by the jury/i)).toBeVisible();

    // Scoped to their own team only: placeholder + RoboLions.
    await expect(teamSelect(page).locator("option")).toHaveCount(2);
    await expect(teamSelect(page).locator("option", { hasText: "RoboLions" })).toHaveCount(1);

    // Mentors may not confirm or delete — no action buttons.
    await expect(page.getByTitle(/bestätigen|confirm/i)).toHaveCount(0);
  });

  test("switching to practice explains that practice runs are excluded", async ({ page, sessions }) => {
    await sessions.signIn("mentor");
    await gotoInEvent(page, "/scoring/entry");

    await page.getByRole("button", { name: /vorbereitung|practice/i }).click();
    await expect(page.getByText(/zählen nicht zur offiziellen rangliste|do not count/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /übungslauf speichern|save practice run/i })).toBeVisible();
  });

  test("a juror can enter scores for every team", async ({ page, sessions }) => {
    await sessions.signIn("juror");
    await gotoInEvent(page, "/scoring/entry");
    const options = teamSelect(page).locator("option");
    await expect(options.filter({ hasText: "RoboLions" })).toHaveCount(1);
    await expect(options.filter({ hasText: "Offline Otters" })).toHaveCount(1);
    // Placeholder + at least the six seeded teams (other specs add teams).
    expect(await options.count()).toBeGreaterThanOrEqual(7);
    // Jurors confirm the seeded official scores.
    await expect(page.getByText(/bestätigt|confirmed/i).first()).toBeVisible();
  });

  test("the scoreboard ranks the seeded teams", async ({ page, sessions }) => {
    await sessions.signIn("guest");
    await gotoInEvent(page, "/scoreboard");
    await expect(page.getByRole("heading", { name: /^(rangliste|ranking)$/i })).toBeVisible();
    await expect(page.getByRole("main").getByText("RoboLions").first()).toBeVisible();
    await expect(page.getByRole("main").getByText("Circuit Breakers").first()).toBeVisible();
  });
});
