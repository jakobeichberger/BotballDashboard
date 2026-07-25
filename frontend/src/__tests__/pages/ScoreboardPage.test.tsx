import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import ScoreboardPage from "@/pages/ScoreboardPage";
import { api } from "@/lib/api";

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

function mockApi(activeSeason: any = SEASON, overrides: Record<string, any> = {}) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/seasons/active") return Promise.resolve({ data: activeSeason });
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
      <MemoryRouter>
        <ScoreboardPage />
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

  it("renders the seeding empty state once the active season loads", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByText(/noch keine wertungen/i)).toBeInTheDocument();
  });

  it("shows the no-season message when there is no active season", async () => {
    mockApi(null);
    renderPage();
    expect(await screen.findByText(/keine aktive saison gefunden/i)).toBeInTheDocument();
  });
});
