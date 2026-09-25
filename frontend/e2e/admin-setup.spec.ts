import { expect, mainNav, openNav, reloadApp, test, uniqueSuffix } from "./helpers";

/*
 * Organizer setup: create a season (which brings its main event), switch to
 * that event, register a team and switch modules off and on again.
 */

test("admin creates a season, registers a team and toggles modules", async ({ page, sessions }) => {
  const seasonName = `E2E Saison ${uniqueSuffix()}`;
  const eventName = `${seasonName} – Main Event`;

  await sessions.signIn("admin");

  // 1. New season (Admin-Einstellungen → Saisons).
  await openNav(page, /admin-einstellungen|admin settings/i);
  await page.getByRole("link", { name: /^(saisons|seasons)$/i }).click();
  await page.getByRole("button", { name: /saison anlegen|add season/i }).click();
  await page.getByPlaceholder("Botball 2027").fill(seasonName);
  await page.getByRole("button", { name: /^(anlegen|create)$/i }).click();
  const seasonRow = page.getByRole("row", { name: new RegExp(seasonName) });
  await expect(seasonRow).toContainText(/entwurf|draft/i);

  // 2. Its main event appears in the event switcher.
  // A reload: the event list is cached for a while.
  await reloadApp(page, "/");
  const switcher = page.getByRole("combobox", { name: /^(event)$/i });
  await expect(switcher.locator("option", { hasText: eventName })).toHaveCount(1);
  await switcher.selectOption({ label: eventName });
  await expect(page.getByRole("banner")).toContainText(eventName);

  // 3. Register a seeded team for the new event.
  await openNav(page, /event-verwaltung|event setup/i);
  const teams = page.locator("section").filter({ has: page.getByRole("heading", { name: /^teams \(/i }) });
  await expect(teams.getByRole("heading", { name: /teams \(0\)/i })).toBeVisible();
  await teams.getByRole("combobox").first().selectOption({ label: "Servo Squad" });
  await teams.getByRole("button", { name: /team registrieren|register team/i }).click();
  await expect(teams.getByRole("heading", { name: /teams \(1\)/i })).toBeVisible();
  await expect(teams.getByRole("listitem").filter({ hasText: "Servo Squad" })).toBeVisible();

  // 4. Switch the robot gallery off: its navigation entry disappears …
  const gallery = page.getByRole("checkbox", { name: /roboter-galerie|robot gallery/i });
  const galleryLink = mainNav(page).getByRole("link", { name: /^(roboter|robots)$/i });
  await expect(galleryLink).toBeVisible();
  await gallery.uncheck();
  await page.getByRole("button", { name: /event speichern|save event/i }).click();
  await expect(page.getByText(/event gespeichert|event saved/i)).toBeVisible();
  await expect(galleryLink).toHaveCount(0);

  // … and comes back when it is switched on again.
  await gallery.check();
  await page.getByRole("button", { name: /event speichern|save event/i }).click();
  await expect(galleryLink).toBeVisible();
});
