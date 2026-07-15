import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import DEPage from "@/pages/DEPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn() } }));

const SEASON = { id: "s1", year: 2026 };

function mockApi(teams: any[] = [], existing: any[] = []) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/seasons/active") return Promise.resolve({ data: SEASON });
    if (url === "/teams") return Promise.resolve({ data: teams });
    if (url.includes("/de-results")) return Promise.resolve({ data: existing });
    return Promise.resolve({ data: null });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DEPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DEPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the heading and save button", () => {
    mockApi();
    renderPage();
    expect(screen.getByRole("heading", { name: /double elimination/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /speichern/i })).toBeInTheDocument();
  });

  it("renders the table headers", () => {
    mockApi();
    renderPage();
    expect(screen.getByRole("columnheader", { name: /team/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /bracket$/i })).toBeInTheDocument();
  });

  it("renders a row per team once teams load", async () => {
    mockApi([{ id: "t1", name: "Alpha", team_number: "1" }]);
    renderPage();
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
  });
});
