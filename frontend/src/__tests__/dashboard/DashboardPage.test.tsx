import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import DashboardPage from "@/pages/DashboardPage";
import { useAuthStore } from "@/store/authStore";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

const SEASON = { id: "s1", name: "Saison 2026", year: 2026, phases: [] };

function mockApi(overrides: Record<string, any> = {}) {
  const data: Record<string, any> = {
    "/seasons/active": SEASON,
    "/dashboard/announcements": [{ id: "a", title: "Ankündigung X" }],
    "/dashboard/stats": { teams: 4, matches: 8, papers: 2, print_jobs: 1 },
    "/papers": [{ id: "p1", title: "Paper Q", status: "submitted" }],
    "/teams": [{ id: "t1", name: "Alpha" }],
    ...overrides,
  };
  (api.get as any).mockImplementation((url: string) => {
    if (url.includes("/ranking/extended")) {
      return Promise.resolve({ data: [{ team_id: "t1", rank: 1, seed_score: 10 }] });
    }
    return Promise.resolve({ data: data[url] ?? null });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function setUser(u: any) {
  useAuthStore.setState({ accessToken: "tok", user: u });
}

describe("DashboardPage (role-adaptive)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
  });

  it("renders the admin dashboard for a superuser", async () => {
    setUser({ id: "u1", display_name: "Dev Admin", is_superuser: true, roles: [] });
    renderPage();
    expect(await screen.findByTestId("admin-dashboard")).toBeInTheDocument();
    expect(screen.getByText("Administrator")).toBeInTheDocument();
    expect(screen.getByText(/willkommen, dev admin/i)).toBeInTheDocument();
    // stats loaded
    await waitFor(() => expect(screen.getByText("4")).toBeInTheDocument());
  });

  it("renders the reviewer dashboard for the reviewer role", async () => {
    setUser({ id: "u2", display_name: "Rita", is_superuser: false, roles: [{ name: "reviewer" }] });
    renderPage();
    expect(await screen.findByTestId("reviewer-dashboard")).toBeInTheDocument();
    expect(screen.getByText("Reviewer")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Paper Q")).toBeInTheDocument());
  });

  it("renders the user dashboard for a mentor", async () => {
    setUser({ id: "u3", display_name: "Max", is_superuser: false, roles: [{ name: "mentor" }] });
    renderPage();
    expect(await screen.findByTestId("user-dashboard")).toBeInTheDocument();
    expect(screen.getByText("Teilnehmer")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());
  });

  it("shows the active season in the header", async () => {
    setUser({ id: "u1", display_name: "A", is_superuser: true, roles: [] });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/aktive saison: saison 2026 \(2026\)/i)).toBeInTheDocument()
    );
  });

  it("only fetches admin stats for admins (no stats call for users)", async () => {
    setUser({ id: "u3", display_name: "Max", is_superuser: false, roles: [{ name: "guest" }] });
    renderPage();
    await screen.findByTestId("user-dashboard");
    const calledUrls = (api.get as any).mock.calls.map((c: any[]) => c[0]);
    expect(calledUrls).not.toContain("/dashboard/stats");
  });
});
