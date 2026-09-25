import { EVENT_SLUG, expect, openNav, pdfFile, reloadApp, test, uniqueSuffix } from "./helpers";
import type { Page } from "@playwright/test";

/*
 * Paper review cycle across four people: the team's mentor submits, the
 * organizer assigns a reviewer, the reviewer reviews, the organizer decides
 * and finalizes, and the team reads the released feedback.
 */

const COMMENT = "Starke Kamera-Erkennung, sauber beschrieben.";

async function openPaper(page: Page, title: string) {
  await openNav(page, /paper-review|paper review/i);
  await page.getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
}

/** Show what the others changed meanwhile (the app caches data for 30 s). */
async function reloadPaper(page: Page, title: string) {
  await reloadApp(page);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
}

test("paper cycle: submit, review, finalize, feedback", async ({ page, sessions }) => {
  test.slow(); // four sessions in one test

  // Arrange: a team of its own per run (one paper per team and season).
  const suffix = uniqueSuffix();
  const teamName = `E2E Paper ${suffix}`;
  const title = `Greifer mit Kamera ${suffix}`;
  const api = await sessions.api("admin");
  const event = (await api.get("/v1/events")).find((item: { slug: string }) => item.slug === EVENT_SLUG);
  const mentor = (await api.get("/auth/users")).find((user: { email: string }) => user.email === "mentor2@test.local");
  const team = await api.post("/teams", {
    name: teamName,
    school: `Schule ${suffix}`,
    country: "AT",
    members: [{ name: mentor.display_name, user_id: mentor.id, role: "mentor" }],
  });
  await api.post(`/v1/events/${event.id}/registrations`, { team_id: team.id });

  // 1. The mentor submits the paper with its PDF.
  await sessions.signIn("mentor2");
  await openNav(page, /paper-review|paper review/i);
  await page.getByRole("button", { name: /paper einreichen|submit paper/i }).click();
  const form = page.getByRole("dialog");
  await form.getByRole("combobox", { name: /team/i }).selectOption({ label: teamName });
  await form.getByRole("textbox", { name: /titel|title/i }).fill(title);
  await form.locator('input[type="file"]').setInputFiles(pdfFile());
  await form.getByRole("button", { name: /^(einreichen|submit)$/i }).click();
  await expect(page.getByRole("row", { name: new RegExp(title) })).toContainText(/eingereicht|submitted/i);

  // 2. The organizer assigns the reviewer.
  const admin = await sessions.open("admin");
  await openPaper(admin, title);
  await admin.getByLabel(/reviewer zuweisen|assign reviewer/i).selectOption({ label: "E2E Reviewer (reviewer@test.local)" });
  await admin.getByRole("button", { name: /^(zuweisen|assign)$/i }).click();
  await expect(admin.getByRole("cell", { name: "E2E Reviewer", exact: true })).toBeVisible();

  // 3. The reviewer scores all five criteria and submits.
  const reviewer = await sessions.open("reviewer");
  await openPaper(reviewer, title);
  const review = reviewer.getByRole("region", { name: /meine bewertung|my review/i });
  const scores = review.getByRole("spinbutton");
  await expect(scores).toHaveCount(5);
  for (let index = 0; index < 5; index++) await scores.nth(index).fill("8");
  await review.getByLabel(/empfehlung|recommendation/i).selectOption("accept");
  await review.getByLabel(/gesamtkommentar|overall comment/i).fill(COMMENT);
  await review.getByRole("button", { name: /bewertung abgeben|submit review/i }).click();
  // The app's own confirmation dialog (lib/confirm), not window.confirm.
  await reviewer.getByRole("dialog").getByRole("button", { name: /^(bestätigen|confirm)$/i }).click();
  await expect(review.getByText(/^(abgegeben|submitted)$/i).first()).toBeVisible();

  // 4. The organizer accepts the paper and finalizes the score.
  await reloadPaper(admin, title);
  await expect(admin.getByText(/alle reviews \(1\)|all reviews \(1\)/i)).toBeVisible();
  await admin.getByLabel(/status ändern|change status/i).selectOption("accepted");
  await admin.getByRole("button", { name: /^(anwenden|apply)$/i }).click();
  await expect(admin.getByRole("main").getByText(/^(angenommen|accepted)$/i).first()).toBeVisible();
  await admin.getByRole("button", { name: /bewertung finalisieren|finalize/i }).click();
  await expect(admin.getByText(/endergebnis|final score/i)).toBeVisible();
  await expect(admin.getByText("80%")).toBeVisible();

  // 5. The team reads the released feedback and the result.
  await openPaper(page, title);
  const feedback = page.getByRole("region", { name: /feedback der reviewer|reviewer feedback/i });
  await expect(feedback).toContainText(COMMENT);
  await expect(feedback).toContainText(/annehmen|accept/i);
  await expect(page.getByText("80%")).toBeVisible();
});
