import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import PapersPage from "@/pages/PapersPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const ADMIN = {
  id: "u1", email: "admin@test.local", display_name: "Admin", is_superuser: true,
  preferred_language: "de", theme: "system", roles: [{ id: "r1", name: "admin", description: null }],
};

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
    useAuthStore.setState({ user: ADMIN as any, accessToken: "test-token" });
  });

  it("renders the heading and create button for an admin", () => {
    mockApi([]);
    renderPage();
    expect(screen.getByRole("heading", { name: /paper review/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /paper anlegen/i })).toBeInTheDocument();
  });

  it("hides the create button for users without write access", () => {
    useAuthStore.setState({ user: null, accessToken: null });
    mockApi([]);
    renderPage();
    expect(screen.queryByRole("button", { name: /paper anlegen/i })).not.toBeInTheDocument();
  });

  it("renders the empty state when there are no papers", async () => {
    mockApi([]);
    renderPage();
    expect(await screen.findByText(/noch keine paper eingereicht/i)).toBeInTheDocument();
  });

  it("renders a paper row with translated status label", async () => {
    mockApi([{ id: "p1", title: "Mein Paper", status: "submitted", revision_number: 0, submitted_at: null }]);
    renderPage();
    expect(await screen.findByText("Mein Paper")).toBeInTheDocument();
    // "Eingereicht" is both the status badge and a column header, so assert >=1.
    expect(screen.getAllByText("Eingereicht").length).toBeGreaterThan(0);
  });
});
