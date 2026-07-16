import { test, expect } from "@playwright/test";
import { login, USERS } from "./helpers";

test.describe("bot gallery", () => {
  test("lists seeded bots and opens a detail page", async ({ page }) => {
    await login(page, USERS.admin);
    await page.getByRole("link", { name: /bot-galerie/i }).click();

    await expect(page.getByRole("heading", { name: /bot-galerie/i })).toBeVisible();
    const card = page.getByRole("link", { name: /robolion x1/i }).first();
    await expect(card).toBeVisible();

    await card.click();
    await expect(page.getByRole("heading", { name: /robolion x1/i })).toBeVisible();
    // The write-up of how the robot works is the point of the gallery.
    await expect(page.getByRole("heading", { name: /funktionsweise/i })).toBeVisible();
    await expect(page.getByText(/differentialantrieb/i)).toBeVisible();
    // Internal bots link back to their team.
    await expect(page.getByRole("link", { name: /robolions/i })).toBeVisible();
  });

  test("filters external teams", async ({ page }) => {
    await login(page, USERS.admin);
    await page.goto("/bots");
    // Wait for the gallery to have loaded before filtering.
    await expect(page.getByText(/robolion x1/i)).toBeVisible();

    await page.getByLabel("Teams filtern").selectOption("external");
    await expect(page.getByText(/zurich crusher/i)).toBeVisible();
    await expect(page.getByText(/robolion x1/i)).toHaveCount(0);

    await page.getByLabel("Teams filtern").selectOption("own");
    await expect(page.getByText(/robolion x1/i)).toBeVisible();
    await expect(page.getByText(/zurich crusher/i)).toHaveCount(0);
  });

  test("a guest cannot create bots", async ({ page }) => {
    await login(page, USERS.guest);
    await page.goto("/bots");
    await expect(page.getByRole("heading", { name: /bot-galerie/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /bot anlegen/i })).toHaveCount(0);
  });
});
