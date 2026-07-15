import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import TeamsPage from "@/pages/TeamsPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));

function mockApi(teams: any[] = []) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/teams") return Promise.resolve({ data: teams });
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
  });
});
