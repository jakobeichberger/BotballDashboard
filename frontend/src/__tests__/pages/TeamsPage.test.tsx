import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import TeamsPage from "@/pages/TeamsPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

function mockApi(teams: any[] = []) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/teams") return Promise.resolve({ data: teams });
    if (url === "/seasons/competition-levels/all") return Promise.resolve({ data: [] });
    if (url.startsWith("/teams/")) {
      const team = teams.find((item) => url === `/teams/${item.id}`);
      return Promise.resolve({ data: team ? { ...team, notes: null, members: [] } : null });
    }
    return Promise.resolve({ data: null });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TeamsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TeamsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: "token",
      user: { id: "admin", email: "admin@example.org", display_name: "Admin", is_superuser: true, preferred_language: "de", theme: "system", roles: [] },
    });
  });

  it("renders the heading and add button", () => {
    mockApi([]);
    renderPage();
    expect(screen.getByRole("heading", { name: /teams/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /team hinzufügen/i })).toBeInTheDocument();
  });

  it("renders the empty state when there are no teams", async () => {
    mockApi([]);
    renderPage();
    expect(await screen.findByText(/noch keine teams angelegt/i)).toBeInTheDocument();
  });

  it("renders team cards when teams are returned", async () => {
    mockApi([
      { id: "t1", name: "Alpha", team_number: "1", is_active: true, school: "School A", city: "Wien", country: "AT" },
    ]);
    renderPage();
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("School A")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /alpha bearbeiten/i })).toBeInTheDocument();
  });

  it("hides write actions without teams:write", async () => {
    useAuthStore.setState({
      user: { id: "reader", email: "reader@example.org", display_name: "Reader", is_superuser: false, preferred_language: "de", theme: "system", roles: [], permissions: ["teams:read"] },
    });
    mockApi([{ id: "t1", name: "Alpha", team_number: "1", is_active: true, country: "AT" }]);
    renderPage();
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /team hinzufügen/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /alpha bearbeiten/i })).not.toBeInTheDocument();
  });
});
