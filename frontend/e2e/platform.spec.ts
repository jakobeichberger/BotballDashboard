import { EVENT_SLUG, expect, mainNav, openNav, test } from "./helpers";

test("the public scoreboard shows the ranking without signing in", async ({ page }) => {
  // Anonymous on purpose: the public board must work without a session.
  await page.goto(`/public/${EVENT_SLUG}`);
  await expect(page.getByText("Botball Live")).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E Regional" })).toBeVisible();
  await expect(mainNav(page)).toHaveCount(0);
  // Seeded seeding results, best first.
  const rows = page.getByRole("row");
  await expect(rows.filter({ hasText: "RoboLions" })).toBeVisible();
  await expect(rows.filter({ hasText: "Circuit Breakers" })).toBeVisible();
  const order = await rows.allInnerTexts();
  const lions = order.findIndex((text) => text.includes("RoboLions"));
  const breakers = order.findIndex((text) => text.includes("Circuit Breakers"));
  expect(lions).toBeLessThan(breakers);
});

test.describe("signed in as admin", () => {
  test.beforeEach(async ({ sessions }) => {
    await sessions.signIn("admin");
  });

  test("admin can open setup and schedule", async ({ page }) => {
    await openNav(page, /event-verwaltung|event setup/i);
    await expect(page.getByRole("heading", { name: /event-verwaltung|event setup/i })).toBeVisible();
    await openNav(page, /^(zeitplan|schedule)$/i);
    await expect(page.getByRole("heading", { name: /zeitplan|schedule/i })).toBeVisible();
  });

  test("the scoring page offers the dynamic official scoring form", async ({ page }) => {
    await openNav(page, /^(wertung|scoring)$/i);
    await expect(page.getByRole("heading", { name: /mobile wertung|mobile scoring/i })).toBeVisible();
    await expect(page.getByRole("spinbutton", { name: /objekte/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /prüfen & absenden|review & submit/i })).toBeVisible();
  });

  test("paper review and printing workspaces are reachable", async ({ page }) => {
    await openNav(page, /paper-review|paper review/i);
    await expect(page.getByRole("heading", { name: /paper/i }).first()).toBeVisible();
    await openNav(page, /3d-druck|3d printing/i);
    await expect(page.getByRole("heading", { name: /3d-druck|3d printing/i })).toBeVisible();
  });
});
