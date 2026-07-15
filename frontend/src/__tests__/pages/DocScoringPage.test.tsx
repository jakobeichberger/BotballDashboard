import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import DocScoringPage from "@/pages/DocScoringPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), patch: vi.fn() } }));

const SEASON = { id: "s1", year: 2026, use_documentation_scoring: true, use_paper_scoring: true };

function mockApi(teams: any[] = [], papers: any[] = []) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/seasons/active") return Promise.resolve({ data: SEASON });
    if (url === "/teams") return Promise.resolve({ data: teams });
    if (url.includes("/doc-scores")) return Promise.resolve({ data: [] });
    if (url === "/papers") return Promise.resolve({ data: papers });
    return Promise.resolve({ data: null });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DocScoringPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DocScoringPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the heading and save button", () => {
    mockApi();
    renderPage();
    expect(screen.getByRole("heading", { name: /dokumentation & paper/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /speichern/i })).toBeInTheDocument();
  });

  it("renders both tab buttons once the season loads", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByRole("button", { name: /dokumentation \(p1\/p2\/p3 \+ onsite\)/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /paper-score/i })).toBeInTheDocument();
  });

  it("renders a documentation row per team once teams load", async () => {
    mockApi([{ id: "t1", name: "Alpha", team_number: "1" }]);
    renderPage();
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
  });
});
