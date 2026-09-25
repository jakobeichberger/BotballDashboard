import { expect, gotoInEvent, openNav, test } from "./helpers";

const GALLERY_HEADING = /bot-galerie|robot gallery/i;
const TEAM_FILTER = /teams filtern|filter teams/i;

test.describe("bot gallery", () => {
  test("lists the seeded bots and opens a detail page", async ({ page, sessions }) => {
    await sessions.signIn("admin");
    await openNav(page, /^(roboter|robots)$/i);

    await expect(page.getByRole("heading", { name: GALLERY_HEADING })).toBeVisible();
    const card = page.getByRole("link", { name: /robolion x1/i }).first();
    await expect(card).toBeVisible();

    await card.click();
    await expect(page.getByRole("heading", { name: /robolion x1/i })).toBeVisible();
    // The write-up of how the robot works is the point of the gallery.
    await expect(page.getByRole("heading", { name: /funktionsweise|how it works/i })).toBeVisible();
    await expect(page.getByText(/differentialantrieb/i)).toBeVisible();
    // Internal bots link back to their team.
    await expect(page.getByRole("main").getByRole("link", { name: /robolions/i })).toBeVisible();
  });

  test("filters own and external teams", async ({ page, sessions }) => {
    await sessions.signIn("admin");
    await gotoInEvent(page, "/bots");
    // Wait for the gallery to have loaded before filtering.
    await expect(page.getByText(/robolion x1/i)).toBeVisible();

    await page.getByLabel(TEAM_FILTER).selectOption("external");
    await expect(page.getByText(/zurich crusher/i)).toBeVisible();
    await expect(page.getByText(/robolion x1/i)).toHaveCount(0);

    await page.getByLabel(TEAM_FILTER).selectOption("own");
    await expect(page.getByText(/robolion x1/i)).toBeVisible();
    await expect(page.getByText(/zurich crusher/i)).toHaveCount(0);
  });

  test("a guest sees the gallery but cannot create bots", async ({ page, sessions }) => {
    await sessions.signIn("guest");
    await gotoInEvent(page, "/bots");
    await expect(page.getByRole("heading", { name: GALLERY_HEADING })).toBeVisible();
    await expect(page.getByText(/robolion x1/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /bot anlegen|add bot/i })).toHaveCount(0);
  });
});
