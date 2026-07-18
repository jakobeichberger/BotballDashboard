import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import PrintingPage from "@/pages/PrintingPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));

function mockApi(jobs: any[] = []) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/printing/jobs") return Promise.resolve({ data: jobs });
    return Promise.resolve({ data: null });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PrintingPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PrintingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: { id: "admin", display_name: "Admin", is_superuser: true, roles: [] } as any,
    });
  });

  it("renders the heading and new job button", () => {
    mockApi([]);
    renderPage();
    expect(screen.getByRole("heading", { name: /3d-druck/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /druckauftrag/i })).toBeInTheDocument();
  });

  it("renders the empty state when there are no jobs", async () => {
    mockApi([]);
    renderPage();
    expect(await screen.findByText(/noch keine druckaufträge/i)).toBeInTheDocument();
  });

  it("renders a print job row", async () => {
    mockApi([
      { id: "j1", file_name: "part.stl", material: "PLA", status: "queued", estimated_grams: 20, estimated_minutes: 60 },
    ]);
    renderPage();
    expect(await screen.findByText("part.stl")).toBeInTheDocument();
    expect(screen.getByText("PLA")).toBeInTheDocument();
  });
});
