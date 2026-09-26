import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import ScoreboardPage from "@/pages/ScoreboardPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

// The ranking tabs on the event day (review 2026-09, #5: ScoreboardPage had
// 39 % line coverage): seeding with categories and red cards, DE brackets,
// six aerial runs, the overall ranking with the season's columns.
vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));
vi.mock("@/hooks/useAuth", () => ({ useCurrentUser: () => ({ data: { id: "u1", roles: [] } }) }));
vi.mock("@/modules/scoring/extras/DEPlacementPanel", () => ({ default: () => <div data-testid="de-placements" /> }));

const get = api.get as ReturnType<typeof vi.fn>;

const SEASON = {
  id: "s1",
  year: 2026,
  use_seeding: true,
  use_double_elimination: true,
  use_paper_scoring: true,
  use_documentation_scoring: false,
  use_aerial: true,
  active_categories: ["botball", "open"],
};

const SEEDING = [
  { rank: 1, team_id: "t1", team_name: "Alpha", category: "botball", seed_score: 412.5, best_score: 420, average_score: 400, rounds_played: 3, tiebreaker: "3. Lauf" },
  { rank: null, disqualified: true, team_id: "t2", team_name: null, category: "open", seed_score: 0, best_score: 0, average_score: 0, rounds_played: 1 },
];
const OVERALL = [
  { rank: 1, team_id: "t1", team_name: "Alpha", category: "botball", overall_score: 0.9123, seeding_score: 1, de_score: 0.75, paper_score: 0.5, doc_score: null },
  { rank: 2, team_id: "t3", team_name: "Gamma", category: "open", overall_score: 0.5, seeding_score: 0.5, de_score: null, paper_score: null, doc_score: null, values: { de_score: 0.25 } },
];
const DE = [
  { id: "d2", team_id: "t3", bracket: "A", de_rank: 2, bracket_score: 0.5, de_score: 0.1 },
  { id: "d1", team_id: "t1", bracket: "A", de_rank: 1, bracket_score: 1, de_score: null },
];
const AERIAL = [
  { rank: 1, team_id: "t4", team_name: "Delta", category: "aerial", runs: [10, 11, 12, 13, 14.5, null], score: 13.2 },
];

function mockApi() {
  get.mockImplementation((url: string) => {
    if (url === "/v1/events/e1") return Promise.resolve({ data: { id: "e1", season_id: "s1" } });
    if (url === "/seasons/s1") return Promise.resolve({ data: SEASON });
    if (url.startsWith("/scoring/events/e1/ranking/extended")) return Promise.resolve({ data: SEEDING });
    if (url.startsWith("/scoring/events/e1/ranking/overall")) return Promise.resolve({ data: OVERALL });
    if (url === "/scoring/events/e1/de-results") return Promise.resolve({ data: DE });
    if (url === "/scoring/events/e1/aerial-ranking") return Promise.resolve({ data: AERIAL });
    return Promise.resolve({ data: [] });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/events/e1/scoreboard"]}>
        <Routes>
          <Route path="/events/:eventId/scoreboard" element={<ScoreboardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const tab = (name: string) => screen.getByRole("button", { name });

describe("ScoreboardPage tabs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
    useAuthStore.setState({
      user: { id: "u1", is_superuser: false, roles: [], permissions: ["scoring:read"] } as never,
    });
  });

  it("offers one tab per active competition part", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: "Seeding" })).toHaveAttribute("aria-pressed", "true");
    for (const name of ["Double Elim.", "Aerial", "Gesamtranking"]) expect(tab(name)).toBeInTheDocument();
  });

  it("lists the seeding with category, tie-breaker and red cards; filters by category", async () => {
    renderPage();
    const alpha = (await screen.findByRole("link", { name: "Alpha" })).closest("tr")!;
    expect(within(alpha).getByText("1")).toBeInTheDocument();
    expect(within(alpha).getByText("3. Lauf")).toBeInTheDocument();
    expect(within(alpha).getByText("412,5000")).toBeInTheDocument();
    // Disqualified: no rank, and a team without a name still gets a row.
    const dq = screen.getByRole("link", { name: "Unbekanntes Team" }).closest("tr")!;
    expect(within(dq).getByTitle("Disqualifiziert (rote Karte)")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Kategorie" })).toBeInTheDocument();

    const filters = screen.getByRole("button", { name: "Alle" }).parentElement!;
    const open = within(filters).getAllByRole("button")[2];
    fireEvent.click(open);
    await waitFor(() => expect(get).toHaveBeenCalledWith("/scoring/events/e1/ranking/extended?category=open"));
    expect(open).toHaveAttribute("aria-pressed", "true");
  });

  it("shows both DE brackets ordered by rank with the formula DE score", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Double Elim." }));
    const bracketA = (await screen.findByRole("heading", { name: "Bracket A" })).nextElementSibling as HTMLElement;
    await within(bracketA).findByRole("link", { name: "Gamma" });
    const rows = within(bracketA).getAllByRole("row");
    // Header + Alpha (rank 1) before Gamma (rank 2); names come from the overall ranking.
    expect(within(rows[1]).getByRole("link")).toHaveTextContent("Alpha");
    expect(within(rows[2]).getByRole("link")).toHaveTextContent("Gamma");
    // The formula's DE score wins over the stored one (0.75 from de_score, 0.25 from values).
    expect(within(rows[1]).getByText("0,7500")).toBeInTheDocument();
    expect(within(rows[2]).getByText("0,2500")).toBeInTheDocument();
    const bracketB = screen.getByRole("heading", { name: "Bracket B" }).nextElementSibling as HTMLElement;
    expect(within(bracketB).getByText("Keine Einträge")).toBeInTheDocument();
    expect(screen.getByTestId("de-placements")).toBeInTheDocument();
    // Entering results is for scoring:admin only.
    expect(screen.queryByRole("link", { name: "DE-Ergebnisse eingeben" })).not.toBeInTheDocument();
  });

  it("shows six aerial runs when a team flew six", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Aerial" }));
    expect(await screen.findByRole("link", { name: "Delta" })).toBeInTheDocument();
    for (let run = 1; run <= 6; run += 1) {
      expect(screen.getByRole("columnheader", { name: `Run ${run}` })).toBeInTheDocument();
    }
    const row = screen.getByRole("link", { name: "Delta" }).closest("tr")!;
    expect(within(row).getByText("14,5")).toBeInTheDocument();
    expect(within(row).getByText("13,2")).toBeInTheDocument();
  });

  it("shows the overall ranking with the season's columns only", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Gesamtranking" }));
    expect(await screen.findByRole("link", { name: "Gamma" })).toBeInTheDocument();
    for (const name of ["Seeding", "DE", "Paper", "Gesamt"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
    // Documentation scoring is off this season.
    expect(screen.queryByRole("columnheader", { name: "Doku" })).not.toBeInTheDocument();
    const alpha = screen.getByRole("link", { name: "Alpha" }).closest("tr")!;
    expect(within(alpha).getByText("0,9123")).toBeInTheDocument();
  });

  it("gives scoring admins the entry links of every active part", async () => {
    useAuthStore.setState({
      user: { id: "u2", is_superuser: false, roles: [], permissions: ["scoring:admin", "scoring:write"] } as never,
    });
    renderPage();
    const hrefs = async () => {
      await screen.findByRole("link", { name: "DE eingeben" });
      return screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    };
    const links = await hrefs();
    expect(links).toEqual(expect.arrayContaining([
      "/events/e1/scoring/entry",
      "/events/e1/scoring/de",
      "/events/e1/scoring/aerial",
      "/events/e1/scoring/doc",
    ]));
    fireEvent.click(tab("Double Elim."));
    expect(await screen.findByRole("link", { name: "DE-Ergebnisse eingeben" })).toBeInTheDocument();
    fireEvent.click(tab("Aerial"));
    expect(await screen.findByRole("link", { name: "Aerial-Ergebnisse eingeben" })).toBeInTheDocument();
  });
});
