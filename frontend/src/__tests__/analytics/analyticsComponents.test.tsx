import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { daysUntil, type DeadlineEntry, type TeamHistoryRow } from "@/api/analytics";
import { DeadlineList, MonthCalendar, RelativeBadge, SeasonTimelineView } from "@/components/analytics/Deadlines";
import { BoxPlotList } from "@/components/analytics/BoxPlot";
import TeamHistoryPanel from "@/components/analytics/TeamHistoryPanel";
import { heatColor } from "@/components/analytics/chartTheme";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));

beforeAll(() => {
  // recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as any;
});

const NOW = new Date(2026, 8, 24, 10, 0);

function deadline(overrides: Partial<DeadlineEntry>): DeadlineEntry {
  return {
    id: "d1",
    title: "Paper-Einreichung",
    kind: "paper",
    color: "red",
    start: "2026-09-27",
    end: null,
    all_day: true,
    season_id: "s1",
    season_name: "Saison 2026",
    event_id: null,
    description: null,
    done: null,
    ...overrides,
  };
}

describe("daysUntil", () => {
  it("counts whole calendar days", () => {
    expect(daysUntil("2026-09-24", NOW)).toBe(0);
    expect(daysUntil("2026-09-27", NOW)).toBe(3);
    expect(daysUntil("2026-09-20", NOW)).toBe(-4);
  });
});

describe("RelativeBadge", () => {
  it.each([
    [{ start: "2026-09-27" }, "in 3 Tagen"],
    [{ start: "2026-09-25" }, "morgen"],
    [{ start: "2026-09-24" }, "heute"],
    [{ start: "2026-09-01" }, "vorbei"],
    [{ start: "2026-09-27", done: true }, "erledigt"],
  ])("renders %o as %s", (overrides, text) => {
    render(<RelativeBadge entry={deadline(overrides)} now={NOW} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });
});

describe("DeadlineList", () => {
  it("shows an empty hint", () => {
    render(<DeadlineList entries={[]} />);
    expect(screen.getByText(/keine anstehenden deadlines/i)).toBeInTheDocument();
  });

  it("lists entries with kind and season", () => {
    render(<DeadlineList entries={[deadline({}), deadline({ id: "d2", title: "Druckjobs", kind: "printing", color: "green" })]} showSeason now={NOW} />);
    const list = screen.getByRole("list", { name: "Deadlines" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Druckjobs")).toBeInTheDocument();
    expect(screen.getAllByText(/Saison 2026/).length).toBe(2);
  });
});

describe("MonthCalendar", () => {
  it("places deadlines on their day and navigates months", async () => {
    render(<MonthCalendar entries={[deadline({})]} initial={NOW} />);
    expect(screen.getByRole("heading", { name: /september 2026/i })).toBeInTheDocument();
    expect(screen.getByTitle("Paper-Einreichung")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /nächster monat/i }));
    expect(screen.getByRole("heading", { name: /oktober 2026/i })).toBeInTheDocument();
    expect(screen.queryByTitle("Paper-Einreichung")).not.toBeInTheDocument();
  });
});

describe("SeasonTimelineView", () => {
  it("renders events in order with status", () => {
    render(
      <SeasonTimelineView
        timeline={{
          season_id: "s1",
          season_name: "Saison 2026",
          season_year: 2026,
          events: [
            { id: "e1", name: "ECER", event_type: "regional", color: "blue", starts_at: null, ends_at: null, status: "finished", phases: [] },
            {
              id: "e2", name: "GCER", event_type: "gcer", color: "purple", starts_at: null, ends_at: null, status: "active",
              phases: [{ id: "p1", name: "Seeding", phase_type: "seeding", starts_at: null, ends_at: null, status: "active" }],
            },
          ],
        }}
      />,
    );
    const items = within(screen.getByRole("list", { name: /ablauf saison 2026/i })).getAllByText(/CER$/);
    expect(items.map((i) => i.textContent)).toEqual(["ECER", "GCER"]);
    expect(screen.getByText("abgeschlossen")).toBeInTheDocument();
    expect(screen.getAllByText("aktiv")).toHaveLength(2);
  });
});

describe("BoxPlotList", () => {
  it("renders one accessible row per box", () => {
    render(
      <BoxPlotList
        ariaLabel="Boxplots"
        rows={[
          { label: "Runde 1", box: { n: 4, min: 10, q1: 20, median: 30, q3: 40, max: 50, mean: 30 } },
          { label: "Runde 2", box: { n: 0, min: null, q1: null, median: null, q3: null, max: null, mean: null } },
        ]}
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("img", { name: /runde 1: min 10,0, q1 20,0, median 30,0/i })).toBeInTheDocument();
  });
});

describe("heatColor", () => {
  it("is transparent without a value and darker for higher ratios", () => {
    expect(heatColor(null)).toBe("transparent");
    const alpha = (c: string) => Number(c.match(/([\d.]+)\)$/)?.[1]);
    expect(alpha(heatColor(1))).toBeGreaterThan(alpha(heatColor(0.2)));
  });
});

describe("TeamHistoryPanel", () => {
  const row = (overrides: Partial<TeamHistoryRow>): TeamHistoryRow => ({
    team_id: "t1", team_name: "Alpha", team_number: null, season_id: "s", season_name: "Saison", season_year: 2025,
    event_id: "e1", event_name: "ECER 2025", event_type: "regional", starts_at: null, category: "botball",
    seeding_rank: 3, seeding_score: 120, seeding_teams: 10, best_score: 150, official_runs: 3, official_avg: 110,
    overall_rank: 2, overall_score: 0.8123, overall_teams: 10, de_score: null, doc_score: null, paper_score: null,
    ...overrides,
  });

  it("shows an empty state", () => {
    render(<MemoryRouter><TeamHistoryPanel rows={[]} /></MemoryRouter>);
    expect(screen.getByText(/noch keine event-teilnahmen/i)).toBeInTheDocument();
  });

  it("renders the table and charts for several events", () => {
    render(
      <MemoryRouter>
        <TeamHistoryPanel rows={[row({}), row({ event_id: "e2", event_name: "ECER 2026", season_year: 2026, practice_runs: 4, practice_avg: 90 })]} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "ECER 2026" })).toBeInTheDocument();
    expect(screen.getAllByText("3/10")).toHaveLength(2);
    expect(screen.getAllByText("0,812")).toHaveLength(2);
    // Practice column only appears when the API sent practice data.
    expect(screen.getByText("Übung Ø")).toBeInTheDocument();
    expect(screen.getByText("90,0 (4)")).toBeInTheDocument();
    expect(screen.getByTestId("history-score-chart")).toBeInTheDocument();
    expect(screen.getByTestId("history-rank-chart")).toBeInTheDocument();
  });
});
