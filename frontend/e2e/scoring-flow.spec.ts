import { expect, openNav, test } from "./helpers";
import type { Page } from "@playwright/test";

/*
 * The juror's scoring workflow on the event scoring page, on desktop and on a
 * phone. The seed leaves "Byte Busters" and "Offline Otters" without results
 * so the ranking rows below appear only through these flows.
 */

async function openScoring(page: Page) {
  await openNav(page, /^(wertung|scoring)$/i);
  await expect(page.getByRole("heading", { name: /mobile wertung|mobile scoring/i })).toBeVisible();
}

async function enterScore(page: Page, team: string, objects: number) {
  const select = page.getByRole("combobox", { name: /^team$/i });
  const value = await select.locator("option", { hasText: team }).getAttribute("value");
  await select.selectOption(value ?? "");
  await page.getByRole("spinbutton", { name: /objekte/i }).fill(String(objects));
  await page.getByRole("button", { name: /prüfen & absenden|review & submit/i }).click();
}

/** The ranking row of `team` in the page's "current ranking" table. */
const rankingRow = (page: Page, team: string) =>
  page.getByRole("row").filter({ has: page.getByRole("cell", { name: team, exact: true }) });

test.describe("scoring @mobile", () => {
  test("an official score updates the ranking", async ({ page, sessions }) => {
    await sessions.signIn("juror");
    await openScoring(page);

    await enterScore(page, "Byte Busters", 17);
    const dialog = page.getByRole("dialog");
    // The summary shows what is about to become official.
    await expect(dialog.getByTestId("confirm-total")).toHaveText("170.00");
    await dialog.getByRole("button", { name: /verbindlich absenden|submit/i }).click();

    await expect(page.getByText(/wertung wurde offiziell gespeichert|score saved officially/i)).toBeVisible();
    await expect(rankingRow(page, "Byte Busters")).toContainText("170.00");
  });

  test("a score entered offline is queued and synced once back online", async ({ page, context, sessions }) => {
    await sessions.signIn("juror");
    await openScoring(page);

    await context.setOffline(true);
    await expect(page.getByRole("alert").filter({ hasText: /offline/i }).first()).toBeVisible();
    await enterScore(page, "Offline Otters", 15);
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: /lokal speichern|save locally/i }).click();

    await expect(page.getByText(/offline gespeichert|saved offline/i)).toBeVisible();
    const pending = page.getByRole("region", { name: /noch nicht synchronisiert|not synced/i });
    await expect(pending).toContainText("Offline Otters");

    await context.setOffline(false);
    // Reconnecting replays the queue; the entry leaves the list and counts.
    await expect(pending).toHaveCount(0);
    await expect(rankingRow(page, "Offline Otters")).toContainText("150.00");
  });
});
