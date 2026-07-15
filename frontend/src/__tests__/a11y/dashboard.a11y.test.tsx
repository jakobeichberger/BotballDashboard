import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import AdminDashboard from "@/pages/dashboard/AdminDashboard";
import ReviewerDashboard from "@/pages/dashboard/ReviewerDashboard";
import UserDashboard from "@/pages/dashboard/UserDashboard";
import { RankingList, AnnouncementsList } from "@/pages/dashboard/widgets";

expect.extend(toHaveNoViolations);

// color-contrast cannot be computed in jsdom (no layout engine); disable it so
// it doesn't report "incomplete". Everything else is fully checked.
const AXE_OPTS = { rules: { "color-contrast": { enabled: false } } };

/** Render inside <main> + Router so top-level content sits in a landmark. */
function a11yRender(ui: React.ReactNode) {
  return render(
    <MemoryRouter>
      <main>{ui}</main>
    </MemoryRouter>
  );
}

const season = {
  id: "s1",
  name: "Saison 2026",
  year: 2026,
  paper_submission_deadline: "2026-09-01",
  phases: [{ id: "p1", name: "Quali", phase_type: "qualification", is_active: true }],
};

describe("dashboard accessibility (axe)", () => {
  it("AdminDashboard has no a11y violations", async () => {
    const { container } = a11yRender(
      <AdminDashboard
        stats={{ teams: 5, matches: 12, papers: 3, print_jobs: 7 }}
        season={season}
        announcements={[{ id: "a", title: "News", body: "Body", published_at: "2026-06-20T10:00:00Z" }]}
      />
    );
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("ReviewerDashboard has no a11y violations", async () => {
    const { container } = a11yRender(
      <ReviewerDashboard
        papers={[
          { id: "p1", title: "Open A", status: "submitted" },
          { id: "p2", title: "Done", status: "accepted" },
        ]}
        season={season}
        announcements={[{ id: "a", title: "News" }]}
      />
    );
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("UserDashboard has no a11y violations", async () => {
    const { container } = a11yRender(
      <UserDashboard
        season={season}
        ranking={[{ team_id: "t1", rank: 1, seed_score: 30 }]}
        teams={[{ id: "t1", name: "Alpha" }]}
        announcements={[{ id: "a", title: "News" }]}
      />
    );
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("RankingList table has no a11y violations", async () => {
    const { container } = a11yRender(
      <RankingList entries={[{ team_id: "t1", rank: 1, seed_score: 30 }]} teams={{ t1: "Alpha" }} />
    );
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("empty AnnouncementsList has no a11y violations", async () => {
    const { container } = a11yRender(<AnnouncementsList announcements={[]} />);
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });
});
