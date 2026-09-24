import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import StatisticsPage from "@/pages/StatisticsPage";
import PerformancePage from "@/pages/PerformancePage";
import DashboardPage from "@/pages/DashboardPage";
import { AdminStatusPanel, JurorPanel, MentorPanel } from "@/pages/dashboard/roleSections";
import type { AdminSection, EventStatistics, JurorSection, MentorTeam, TeamPerformance } from "@/api/analytics";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as any;
});

function renderAt(path: string, route: string, element: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const JUROR: JurorSection = {
  unconfirmed_count: 2,
  unconfirmed: [
    { match_id: "m1", team_id: "t1", team_name: "Alpha", round_number: 2, total_score: 120, is_disqualified: false, created_at: null, entered_by_name: "Mia", entered_by_team_member: true },
    { match_id: "m2", team_id: "t2", team_name: "Beta", round_number: 1, total_score: 80, is_disqualified: false, created_at: null, entered_by_name: "Jury", entered_by_team_member: false },
  ],
  upcoming_matches: [
    { id: "s1", code: "S-7", round_number: 3, table_number: 2, scheduled_at: null, status: "scheduled", phase_name: "Seeding", teams: [{ team_id: "t1", team_name: "Alpha" }] },
  ],
  open_scans_count: 1,
  open_scans: [{ id: "sc", team_id: "t1", team_name: "Alpha", status: "review", file_name: "sheet.jpg", created_at: null }],
};

const MENTOR_TEAM: MentorTeam = {
  team_id: "t1",
  team_name: "Alpha",
  seeding_rank: 2,
  seed_score: 110,
  seeding_teams: 8,
  next_matches: [],
  paper: null,
  print_jobs: { open: 1, completed: 2, recent: [] },
  latest_scores: [{ match_id: "m9", round_number: 1, total_score: 95, is_practice: true, is_disqualified: false, confirmed: false, created_at: null }],
};

const ADMIN: AdminSection = {
  teams_registered: 4, teams_checked_in: 3, teams_scored: 2, teams_with_paper: 1, papers_total: 2, reviews_pending: 5,
  official_runs: 10, practice_runs: 7, unconfirmed_runs: 4, de_results: 0, doc_scores: 1,
  print_queue: { pending: 1, active: 2, completed: 3, failed: 1 }, generated_at: "2026-09-24T10:00:00Z",
};

describe("role sections", () => {
  it("juror panel lists mentor entries and next matches", () => {
    renderAt("/", "/", <JurorPanel juror={JUROR} />);
    expect(screen.getByText("Mentor-Eintrag")).toBeInTheDocument();
    expect(screen.getByText("S-7")).toBeInTheDocument();
    expect(screen.getByText(/sheet\.jpg/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /auffälligkeiten prüfen/i })).toBeInTheDocument();
  });

  it("mentor panel flags a missing paper and marks practice scores", () => {
    renderAt("/", "/", <MentorPanel teams={[MENTOR_TEAM]} />);
    expect(screen.getByText("nicht eingereicht")).toBeInTheDocument();
    expect(screen.getByText("Übung")).toBeInTheDocument();
    expect(screen.getByText("2. von 8")).toBeInTheDocument();
    expect(screen.getByText("1 offen · 2 fertig")).toBeInTheDocument();
  });

  it("admin panel shows X of N progress", () => {
    renderAt("/", "/", <AdminStatusPanel status={ADMIN} />);
    expect(screen.getByRole("progressbar", { name: "Teams mit Wertung" })).toHaveAttribute("aria-valuenow", "2");
    expect(screen.getByText("2 von 4")).toBeInTheDocument();
    expect(screen.getByText("6 von 10")).toBeInTheDocument(); // confirmed runs
    expect(screen.getByText(/1 Fehler/)).toBeInTheDocument();
  });

  it("leaves out paper and print figures of modules the event does not use", () => {
    renderAt("/", "/", <AdminStatusPanel status={ADMIN} modules={["seeding", "bots"]} />);
    expect(screen.queryByRole("progressbar", { name: "Teams mit eingereichtem Paper" })).not.toBeInTheDocument();
    expect(screen.queryByText("Offene Reviews")).not.toBeInTheDocument();
    expect(screen.queryByText("Druck-Queue")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Teams mit Wertung" })).toBeInTheDocument();
  });

  it("mentor panel hides paper and print jobs when those modules are off", () => {
    renderAt("/", "/", <MentorPanel teams={[MENTOR_TEAM]} modules={["seeding", "paper"]} />);
    expect(screen.getByText("nicht eingereicht")).toBeInTheDocument();
    expect(screen.queryByText("1 offen · 2 fertig")).not.toBeInTheDocument();
  });
});

describe("DashboardPage with summary", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the mentor and deadline sections for a mentor", async () => {
    useAuthStore.setState({ accessToken: "t", user: { id: "u", display_name: "Max", is_superuser: false, roles: [{ name: "mentor" }] } as any });
    (api.get as any).mockImplementation((url: string) => {
      if (url === "/dashboard/summary") {
        return Promise.resolve({
          data: {
            event_id: "e1", juror: null, admin: null, mentor: { teams: [MENTOR_TEAM] },
            deadlines: [{ id: "d", title: "Paper-Einreichung", kind: "paper", color: "red", start: "2099-01-01", end: null, all_day: true, season_id: "s", season_name: "S", event_id: null, description: null, done: false }],
          },
        });
      }
      if (url.endsWith("/registrations") || url.endsWith("/ranking") || url.endsWith("/phases")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: null });
    });
    renderAt("/events/e1/dashboard", "/events/:eventId/dashboard", <DashboardPage />);
    expect(await screen.findByTestId("mentor-panel")).toBeInTheDocument();
    expect(screen.getByText("Paper-Einreichung")).toBeInTheDocument();
    expect(screen.queryByTestId("juror-panel")).not.toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/dashboard/summary", { params: { event_id: "e1" } });
  });
});

const STATS: EventStatistics = {
  event_id: "e1",
  event_name: "ECER",
  include_practice: false,
  overview: { runs: 6, disqualified: 0, teams: 2, unconfirmed: 3, total: null },
  rounds: [{ round_number: 1, n: 2, min: 50, q1: 60, median: 70, q3: 80, max: 90, mean: 70 }],
  fields: [{ key: "cubes", label: "Würfel", n: 6, min: 0, q1: 10, median: 20, q3: 30, max: 40, mean: 20, zero_share: 0.1 }],
  heatmap: {
    fields: [{ key: "cubes", label: "Würfel" }],
    teams: [{ team_id: "t1", team_name: "Alpha", values: [{ key: "cubes", avg: 33.3, ratio: 1 }] }],
  },
  trend: { rounds: [{ round_number: 1, mean: 70, median: 70 }], teams: [{ team_id: "t1", team_name: "Alpha", points: [{ round_number: 1, total_score: 90, match_id: "m1" }], slope: null }] },
  anomalies: [
    {
      match_id: "m1", team_id: "t1", team_name: "Alpha", round_number: 1, total_score: 900, is_practice: false,
      scheduled_match_id: null, confirmed: false, created_at: null, severity: "error",
      reasons: [{ kind: "out_of_range", message: "Würfel: 90 über dem Maximum 20", severity: "error", score: null }],
    },
  ],
};

describe("StatisticsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as any).mockImplementation((url: string) => {
      if (url === "/dashboard/events/e1/statistics") return Promise.resolve({ data: STATS });
      if (url === "/scoring/matches/m1") return Promise.resolve({ data: { id: "m1", total_score: 900, raw_scores: { cubes: 90 }, confirmed_at: null } });
      if (url === "/scoring/matches/m1/revisions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: null });
    });
    (api.put as any).mockResolvedValue({ data: {} });
  });

  it("renders anomalies, heatmap and distributions", async () => {
    renderAt("/events/e1/statistics", "/events/:eventId/statistics", <StatisticsPage />);
    expect(await screen.findByText(/Würfel: 90 über dem Maximum 20/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Würfel" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Alpha" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /runde 1:/i })).toBeInTheDocument();
  });

  it("opens the review dialog and confirms the run", async () => {
    renderAt("/events/e1/statistics", "/events/:eventId/statistics", <StatisticsPage />);
    await userEvent.click(await screen.findByRole("button", { name: /prüfen/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByText("cubes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /bestätigen/i }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/scoring/matches/m1/confirm"));
  });

  it("requests practice runs when toggled", async () => {
    renderAt("/events/e1/statistics", "/events/:eventId/statistics", <StatisticsPage />);
    await screen.findByText(/Würfel: 90/);
    await userEvent.click(screen.getByLabelText(/übungsläufe einbeziehen/i));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/dashboard/events/e1/statistics", { params: { include_practice: true } }),
    );
  });
});

const PERF: TeamPerformance = {
  event_id: "e1", event_name: "ECER", team_id: "t1", team_name: "Alpha", category: "botball", include_practice: true,
  runs: [
    { match_id: "a", round_number: 1, created_at: null, total_score: 80, is_practice: true, is_disqualified: false, phase: "practice", phase_name: null, notes: null, confirmed: false },
    { match_id: "b", round_number: 1, created_at: null, total_score: 100, is_practice: false, is_disqualified: false, phase: "seeding", phase_name: null, notes: null, confirmed: true },
  ],
  summary: { official_runs: 1, official_avg: 100, official_best: 100, practice_runs: 1, practice_avg: 80, practice_best: 80, trend_per_run: 20 },
  fields: [
    { key: "park", label: "Parken", team_avg: 25, field_avg: 10, field_best: 25, delta: 15, share_of_best: 1 },
    { key: "cubes", label: "Würfel", team_avg: 40, field_avg: 60, field_best: 90, delta: -20, share_of_best: 0.44 },
  ],
  strengths: ["park"],
  weaknesses: ["cubes"],
  phases: [
    { phase: "practice", n: 1, min: 80, q1: 80, median: 80, q3: 80, max: 80, mean: 80 },
    { phase: "seeding", n: 1, min: 100, q1: 100, median: 100, q3: 100, max: 100, mean: 100 },
  ],
  season_events: [],
  ranking_preview: { seeding_rank: 3, seeding_score: 100, seeding_teams: 9, points_to_next_rank: 12.5, overall_rank: 4, overall_score: 0.71, overall_teams: 9 },
};

describe("PerformancePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as any).mockImplementation((url: string) => {
      if (url === "/dashboard/events/e1/performance") {
        return Promise.resolve({
          data: [{ team_id: "t1", team_name: "Alpha", team_number: null, official_runs: 1, official_avg: 100, official_best: 100, practice_runs: 1, practice_avg: 80, trend_per_run: 20, seeding_rank: 3, last_run_at: null }],
        });
      }
      if (url === "/dashboard/events/e1/teams/t1/performance") return Promise.resolve({ data: PERF });
      return Promise.resolve({ data: null });
    });
  });

  it("shows the ranking preview, strengths and phase comparison of the selected team", async () => {
    renderAt("/events/e1/performance", "/events/:eventId/performance", <PerformancePage />);
    expect(await screen.findByTestId("team-performance")).toBeInTheDocument();
    expect(screen.getByText("+12.5")).toBeInTheDocument();
    expect(screen.getByText("Stärke")).toBeInTheDocument();
    expect(screen.getByText("Schwäche")).toBeInTheDocument();
    expect(screen.getByTestId("score-trend-chart")).toBeInTheDocument();
    expect(screen.getAllByText("Übung").length).toBeGreaterThan(0);
  });

  it("uses the team from the URL", async () => {
    renderAt("/events/e1/performance?team=t1", "/events/:eventId/performance", <PerformancePage />);
    await screen.findByTestId("team-performance");
    expect(api.get).toHaveBeenCalledWith("/dashboard/events/e1/teams/t1/performance", { params: { include_practice: true } });
  });
});
