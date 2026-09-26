import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import ScoreboardPage from "@/pages/ScoreboardPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));
vi.mock("@/hooks/useAuth", () => ({
  useCurrentUser: () => ({ data: { id: "u1", roles: [] } }),
}));

const SEASON = {
  id: "s1",
  year: 2026,
  use_seeding: true,
  use_double_elimination: false,
  use_paper_scoring: false,
  use_documentation_scoring: false,
  use_aerial: false,
  active_categories: ["botball"],
};

// The page lives under /events/:eventId; its season comes from the event.
function mockApi(season: any = SEASON, overrides: Record<string, any> = {}) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/v1/events/e1") return Promise.resolve({ data: season ? { id: "e1", season_id: season.id } : null });
    if (url === "/seasons/s1") return Promise.resolve({ data: season });
    for (const [key, value] of Object.entries(overrides)) {
      if (url.includes(key)) return Promise.resolve({ data: value });
    }
    if (url.includes("/ranking/extended")) return Promise.resolve({ data: [] });
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
    </QueryClientProvider>
  );
}

describe("ScoreboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the ranking heading", () => {
    mockApi();
    renderPage();
    expect(screen.getByRole("heading", { name: /rangliste/i })).toBeInTheDocument();
  });

  it("renders the seeding empty state once the event's season loads", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByText(/noch keine wertungen/i)).toBeInTheDocument();
  });

  it("shows the organizer links for scoring:admin, not for a role name", async () => {
    mockApi();
    const hrefs = () => screen.queryAllByRole("link").map((a) => a.getAttribute("href"));
    useAuthStore.setState({
      user: { id: "u1", is_superuser: false, roles: [{ name: "admin" }], permissions: ["scoring:read"] } as never,
    });
    const { unmount } = renderPage();
    await screen.findByText(/noch keine wertungen/i);
    expect(hrefs()).not.toContain("/events/e1/scoring/score-sheets");
    expect(hrefs()).not.toContain("/events/e1/scoring/entry");
    unmount();

    useAuthStore.setState({
      user: { id: "u2", is_superuser: false, roles: [{ name: "organizer" }], permissions: ["scoring:admin", "scoring:write"] } as never,
    });
    renderPage();
    await screen.findByText(/noch keine wertungen/i);
    expect(hrefs()).toContain("/events/e1/scoring/score-sheets");
    expect(hrefs()).toContain("/events/e1/scoring/entry");
  });

  it("shows the no-season message when the event cannot be loaded", async () => {
    mockApi(null);
    renderPage();
    expect(await screen.findByText(/keine aktive saison gefunden/i)).toBeInTheDocument();
  });
});
