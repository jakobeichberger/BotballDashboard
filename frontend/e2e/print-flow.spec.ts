import { expect, openNav, reloadApp, stlFile, test, uniqueSuffix } from "./helpers";

/*
 * 3D print job from request to completion: the mentor submits a model, the
 * organizer approves it, queues it on the (manual) E2E printer and marks it
 * done, and the team sees the finished job.
 */

test("print job: request, approve, queue, complete", async ({ page, sessions }) => {
  const fileName = `greifer-${uniqueSuffix()}.stl`;

  // 1. The mentor requests the print with the model file.
  await sessions.signIn("mentor");
  await openNav(page, /3d-druck|3d printing/i);
  await page.getByRole("button", { name: /druckauftrag|print job/i }).click();
  const form = page.getByRole("dialog");
  await form.getByRole("combobox", { name: /team/i }).selectOption({ label: "RoboLions" });
  await form.locator('input[type="file"]').setInputFiles(stlFile(fileName));
  await form.getByRole("spinbutton", { name: /gramm|grams/i }).fill("12");
  await form.getByRole("button", { name: /^(erstellen|create)$/i }).click();
  const row = page.getByRole("row", { name: new RegExp(fileName) });
  await expect(row).toContainText(/ausstehend|pending/i);
  await expect(row).not.toContainText(/ohne datei|no file/i);

  // 2. The organizer approves, queues and completes it.
  const admin = await sessions.open("admin");
  await openNav(admin, /3d-druck|3d printing/i);
  await admin.getByRole("link", { name: fileName }).click();
  await expect(admin.getByRole("heading", { level: 1, name: fileName })).toBeVisible();
  const status = admin.getByRole("main").locator("span[class^='badge']").first();
  await admin.getByRole("button", { name: /^(genehmigen|approve)$/i }).click();
  await expect(status).toHaveText(/genehmigt|approved/i);

  await admin.getByRole("combobox", { name: /^(drucker|printer)$/i }).selectOption({ label: "E2E Drucker" });
  await admin.getByRole("button", { name: /^(einreihen|queue)$/i }).click();
  await expect(status).toHaveText(/warteschlange|queued/i);

  await admin.getByRole("button", { name: /als fertig markieren|mark as done/i }).click();
  await admin.getByRole("spinbutton", { name: /verbrauch|used/i }).fill("11.5");
  await admin.getByRole("button", { name: /^(speichern|save)$/i }).click();
  await expect(status).toHaveText(/fertig|completed/i);
  await expect(admin.getByText("11.5 g")).toBeVisible();

  // 3. The team sees the finished job (reload: the list is cached for 30 s).
  await reloadApp(page);
  await expect(page.getByRole("row", { name: new RegExp(fileName) })).toContainText(/fertig|completed/i);
});
