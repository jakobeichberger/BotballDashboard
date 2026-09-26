import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import PapersPage from "@/pages/PapersPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));

function mockApi(papers: any[] = []) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/papers") return Promise.resolve({ data: papers });
    return Promise.resolve({ data: null });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PapersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PapersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: { id: "admin", display_name: "Admin", is_superuser: true, roles: [] } as any,
    });
  });

  it("renders the heading and submit button", () => {
    mockApi([]);
    renderPage();
    expect(screen.getByRole("heading", { name: /paper review/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /paper einreichen/i })).toBeInTheDocument();
  });

  it("renders the empty state when there are no papers", async () => {
    mockApi([]);
    renderPage();
    expect(await screen.findByText(/noch keine paper eingereicht/i)).toBeInTheDocument();
  });

  it("shows paper statistics to organizers", async () => {
    (api.get as any).mockImplementation((url: string) => {
      if (url === "/papers") return Promise.resolve({ data: [] });
      if (url === "/papers/stats")
        return Promise.resolve({
          data: {
            total: 4, by_status: {}, decided: 2, accepted: 1, rejected: 1, disqualified: 0,
            acceptance_rate: 0.5, average_final_score: 0.72, average_review_score: 7.2,
            criterion_averages: { content: 7, implementation: 7, results: 7, language: 8, format: 7 },
            reviews_submitted: 3, reviews_open: 2, average_revision_rounds: 1.5,
          },
        });
      return Promise.resolve({ data: null });
    });
    renderPage();
    expect(await screen.findByText("Annahmequote")).toBeInTheDocument();
    expect(screen.getByText("50 %")).toBeInTheDocument();
    expect(screen.getByText("72 %")).toBeInTheDocument();
    expect(screen.getByText("7,2 / 10")).toBeInTheDocument();
  });

  it("renders the new statuses", async () => {
    mockApi([
      { id: "p1", title: "A", status: "resubmitted", revision_number: 2, current_version: 3, submitted_at: null },
      { id: "p2", title: "B", status: "disqualified_ai", revision_number: 1, current_version: 1, submitted_at: null },
    ]);
    renderPage();
    expect(await screen.findByText("Neu eingereicht")).toBeInTheDocument();
    expect(screen.getByText("Disqualifiziert (KI)")).toBeInTheDocument();
    expect(screen.getByText("v3")).toBeInTheDocument();
  });

  it("renders a paper row with translated status label", async () => {
    mockApi([{ id: "p1", title: "Mein Paper", status: "submitted", revision_number: 0, submitted_at: null }]);
    renderPage();
    expect(await screen.findByText("Mein Paper")).toBeInTheDocument();
    // "Eingereicht" is both the status badge and a column header, so assert >=1.
    expect(screen.getAllByText("Eingereicht").length).toBeGreaterThan(0);
  });
});
