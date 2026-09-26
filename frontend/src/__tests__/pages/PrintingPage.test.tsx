import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import PrintingPage from "@/pages/PrintingPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { PRINT_REFRESH_MS } from "@/lib/printing";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn() } }));

const PRINTER = {
  id: "p1", name: "Bambu X1", model: null, printer_type: "bambu", is_active: true,
  is_online: true, last_seen: null, current_state: "printing", status_message: "RUNNING",
};

function mockApi(jobs: any[] = [], extra: Record<string, any> = {}) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/printing/jobs") return Promise.resolve({ data: jobs });
    if (url in extra) return Promise.resolve({ data: extra[url] });
    return Promise.resolve({ data: null });
  });
}

let client: QueryClient;

function renderPage(path = "/") {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<PrintingPage />} />
          <Route path="/events/:eventId/printing" element={<PrintingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function asMentor() {
  useAuthStore.setState({
    user: { id: "m", display_name: "Mentor", is_superuser: false, roles: [{ name: "admin" }], permissions: ["printing:read", "printing:write"] } as any,
  });
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

  it("refreshes the job list automatically", async () => {
    mockApi([]);
    renderPage();
    await screen.findByText(/noch keine druckaufträge/i);
    const query = client.getQueryCache().find({ queryKey: ["print-jobs", ""] });
    expect((query?.options as any).refetchInterval).toBe(PRINT_REFRESH_MS);
  });

  it("shows progress, remaining time and rejection reasons", async () => {
    mockApi([
      { id: "j1", file_name: "arm.3mf", material: "PLA", status: "printing", progress: 42, remaining_seconds: 1800, file_url: "/x" },
      { id: "j2", file_name: "big.stl", material: "PLA", status: "rejected", rejection_reason: "Zu groß", file_url: "/x" },
    ]);
    renderPage();
    expect(await screen.findByText(/42% · noch 30 min/)).toBeInTheDocument();
    expect(screen.getByText("Abgelehnt")).toBeInTheDocument();
    expect(screen.getByText("Zu groß")).toBeInTheDocument();
  });

  it("shows printer status to mentors without the adapter form", async () => {
    asMentor();
    mockApi([{ id: "j1", file_name: "own.stl", material: "PLA", status: "pending", file_url: "/x" }], { "/printing/printers": [PRINTER] });
    renderPage();
    expect(await screen.findByText("Bambu X1")).toBeInTheDocument();
    expect(screen.getByText(/druckt · bambu lan/i)).toBeInTheDocument();
    expect(screen.queryByText(/drucker-adapter/i)).not.toBeInTheDocument();
    // Admin actions are gated by printing:admin, not by an "admin" role name.
    expect(screen.queryByRole("button", { name: /freigeben/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zurückziehen/i })).toBeInTheDocument();
  });

  it("uploads the file after creating the job and shows the quota warning", async () => {
    const user = userEvent.setup();
    mockApi([], {
      "/v1/events/e1": { id: "e1", season_id: "s1", name: "ECER" },
      "/v1/events/e1/registrations": [{ id: "r1", team_id: "t1", team_name: "Team One" }],
    });
    (api.post as any).mockImplementation((url: string) => {
      if (url === "/printing/jobs") return Promise.resolve({ data: { id: "j9", quota_warning: "Soft limit exceeded: 4 parts" } });
      return Promise.resolve({ data: { id: "j9" } });
    });
    renderPage("/events/e1/printing");
    await user.click(screen.getByRole("button", { name: /druckauftrag/i }));
    await user.selectOptions(await screen.findByRole("combobox", { name: /team/i }), "t1");
    const file = new File(["solid x\nendsolid x\n"], "gripper.stl", { type: "model/stl" });
    await user.upload(screen.getByLabelText(/datei/i), file);
    await user.click(screen.getByRole("button", { name: /erstellen/i }));

    expect(await screen.findByText(/soft limit exceeded/i)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/printing/jobs", expect.objectContaining({ team_id: "t1", file_name: "gripper.stl", event_id: "e1" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/printing/jobs/j9/file", expect.any(FormData)));
  });
});
