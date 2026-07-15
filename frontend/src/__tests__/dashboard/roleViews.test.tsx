import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AdminDashboard from "@/pages/dashboard/AdminDashboard";
import ReviewerDashboard from "@/pages/dashboard/ReviewerDashboard";
import UserDashboard from "@/pages/dashboard/UserDashboard";

const router = (ui: React.ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>);

const season = {
  id: "s1",
  name: "Saison 2026",
  year: 2026,
  paper_submission_deadline: "2026-09-01",
  phases: [{ id: "p1", name: "Quali", phase_type: "qualification", is_active: true }],
};

describe("AdminDashboard", () => {
  it("renders system KPIs, shortcuts, phases and announcements", () => {
    router(
      <AdminDashboard
        stats={{ teams: 5, matches: 12, papers: 3, print_jobs: 7 }}
        season={season}
        announcements={[{ id: "a", title: "News", body: "Body" }]}
      />
    );
    expect(screen.getByTestId("admin-dashboard")).toBeInTheDocument();
    // KPI values
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    // management shortcuts
    expect(screen.getByRole("link", { name: /teams verwalten/i })).toHaveAttribute("href", "/teams");
    expect(screen.getByRole("link", { name: /einstellungen/i })).toHaveAttribute("href", "/settings");
    // phases + announcements
    expect(screen.getByRole("region", { name: "Phasen" })).toBeInTheDocument();
    expect(screen.getByText("News")).toBeInTheDocument();
  });

  it("defaults KPIs to 0 when stats are missing", () => {
    router(<AdminDashboard season={season} announcements={[]} />);
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(4);
  });
});

describe("ReviewerDashboard", () => {
  const papers = [
    { id: "p1", title: "Open A", status: "submitted" },
    { id: "p2", title: "Open B", status: "under_review" },
    { id: "p3", title: "Done", status: "accepted" },
  ];

  it("splits papers into open queue vs done and shows the deadline", () => {
    router(<ReviewerDashboard papers={papers} season={season} announcements={[]} />);
    expect(screen.getByTestId("reviewer-dashboard")).toBeInTheDocument();
    // queue shows only the 2 open papers
    expect(screen.getByText("Open A")).toBeInTheDocument();
    expect(screen.getByText("Open B")).toBeInTheDocument();
    expect(screen.queryByText("Done")).not.toBeInTheDocument();
    // deadline rendered as a <time>
    expect(document.querySelector("time")).toHaveAttribute("dateTime", "2026-09-01");
  });

  it("handles an empty paper list", () => {
    router(<ReviewerDashboard papers={[]} season={season} announcements={[]} />);
    expect(screen.getByText(/keine paper zur begutachtung/i)).toBeInTheDocument();
  });
});

describe("UserDashboard", () => {
  it("renders top ranking with team names, phases and announcements", () => {
    router(
      <UserDashboard
        season={season}
        ranking={[
          { team_id: "t1", rank: 1, seed_score: 30 },
          { team_id: "t2", rank: 2, seed_score: 20 },
        ]}
        teams={[
          { id: "t1", name: "Alpha" },
          { id: "t2", name: "Beta" },
        ]}
        announcements={[{ id: "a", title: "Hi" }]}
      />
    );
    expect(screen.getByTestId("user-dashboard")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Hi")).toBeInTheDocument();
  });

  it("limits the ranking to the top 5", () => {
    const ranking = Array.from({ length: 8 }, (_, i) => ({
      team_id: `t${i}`,
      rank: i + 1,
      seed_score: 100 - i,
    }));
    router(<UserDashboard season={season} ranking={ranking} teams={[]} announcements={[]} />);
    // header row + 5 data rows
    expect(screen.getAllByRole("row")).toHaveLength(6);
  });
});
