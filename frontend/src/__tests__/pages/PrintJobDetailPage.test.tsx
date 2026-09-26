import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import PrintJobDetailPage from "@/pages/PrintJobDetailPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn() } }));
const confirmSpy = vi.hoisted(() => vi.fn(async () => true));
vi.mock("@/lib/confirm", () => ({ confirmAction: confirmSpy }));

const BASE_JOB = {
  id: "j1", team_id: "t1", season_id: "s1", event_id: "e1", printer_id: "p1", file_name: "arm.3mf",
  file_url: "/api/printing/jobs/j1/file", file_size_bytes: 2048, material: "PLA", color: null,
  estimated_grams: 20, actual_grams: null, estimated_minutes: null, actual_minutes: null,
  status: "pending", priority: 0, progress: null, status_message: null, remaining_seconds: null,
  error_message: null, rejection_reason: null, quota_override: false, spool_id: "s1", notes: null,
  approved_at: null, started_at: null, completed_at: null, created_at: "2026-09-01T10:00:00Z",
};

function mockApi(job: Record<string, unknown>) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/printing/jobs/j1") return Promise.resolve({ data: { ...BASE_JOB, ...job } });
    if (url === "/printing/printers") return Promise.resolve({ data: [{ id: "p1", name: "Bambu X1", is_active: true }] });
    if (url === "/printing/spools") return Promise.resolve({ data: [{ id: "s1", material: "PLA", color: "Rot", brand: null, initial_grams: 1000, remaining_grams: 800 }] });
    return Promise.resolve({ data: [] });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/printing/jobs/j1"]}>
        <Routes>
          <Route path="/printing/jobs/:id" element={<PrintJobDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function setUser(permissions: string[], roles: { name: string }[] = []) {
  useAuthStore.setState({
    user: { id: "u", display_name: "U", is_superuser: false, roles, permissions } as any,
  });
}

describe("PrintJobDetailPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("gates admin actions by printing:admin, not by the admin role", async () => {
    setUser(["printing:read", "printing:write"], [{ name: "admin" }]);
    mockApi({});
    renderPage();
    expect(await screen.findByRole("heading", { name: /arm\.3mf/ })).toBeInTheDocument();
    expect(screen.queryByText(/verwaltung/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /genehmigen/i })).not.toBeInTheDocument();
    // The team may still withdraw its own pending job and download the file.
    expect(screen.getByRole("button", { name: /zurückziehen/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /herunterladen/i })).toBeInTheDocument();
  });

  it("shows admin actions to printing:admin holders", async () => {
    setUser(["printing:read", "printing:admin"]);
    mockApi({});
    renderPage();
    expect(await screen.findByRole("button", { name: /genehmigen/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ablehnen/i })).toBeDisabled();
    expect(screen.getByText(/pla · rot \(800 g\)/i)).toBeInTheDocument();
  });

  it("rejects with a reason", async () => {
    const user = userEvent.setup();
    setUser(["printing:read", "printing:admin"]);
    mockApi({});
    (api.put as any).mockResolvedValue({ data: {} });
    renderPage();
    await user.type(await screen.findByLabelText(/ablehnungsgrund/i), "Zu groß");
    await user.click(screen.getByRole("button", { name: /ablehnen/i }));
    expect(api.put).toHaveBeenCalledWith("/printing/jobs/j1/reject", { reason: "Zu groß" });
  });

  it("records grams and spool when completing", async () => {
    const user = userEvent.setup();
    setUser(["printing:read", "printing:admin"]);
    mockApi({ status: "printing", progress: 55, remaining_seconds: 5400 });
    (api.patch as any).mockResolvedValue({ data: {} });
    renderPage();
    expect(await screen.findByText(/restzeit: 1 h 30 min/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /als fertig markieren/i }));
    const grams = screen.getByLabelText(/verbrauch/i);
    await user.clear(grams);
    await user.type(grams, "31.5");
    await user.selectOptions(screen.getByLabelText(/spule/i), "s1");
    await user.click(screen.getByRole("button", { name: /speichern/i }));
    expect(api.patch).toHaveBeenCalledWith("/printing/jobs/j1", expect.objectContaining({ status: "completed", actual_grams: 31.5, spool_id: "s1" }));
  });

  it("shows the printer error on a failed job", async () => {
    setUser(["printing:read"]);
    mockApi({ status: "failed", error_message: "Nozzle clog" });
    renderPage();
    expect(await screen.findByText(/nozzle clog/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /zurückziehen/i })).not.toBeInTheDocument();
  });

  it("explains a retry refused by the quota and lets a print admin release it after asking", async () => {
    const user = userEvent.setup();
    setUser(["printing:read", "printing:admin"]);
    mockApi({ status: "failed", error_message: "Nozzle clog" });
    const quota = { response: { status: 409, data: { code: "http_409", message: "Hard print limit reached (2 parts; 1 printed, 1 open). Cannot submit more jobs." } } };
    (api.patch as any).mockRejectedValueOnce(quota).mockResolvedValue({ data: {} });
    confirmSpy.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Einreihen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Druckkontingent des Teams .* ist ausgeschöpft/);
    const release = screen.getByRole("button", { name: "Trotz Kontingent freigeben" });
    // Cancelled confirmation: nothing is sent.
    await user.click(release);
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(api.patch).toHaveBeenCalledTimes(1);
    await user.click(release);
    expect(api.patch).toHaveBeenLastCalledWith("/printing/jobs/j1", { status: "queued", printer_id: "p1", quota_override: true });
  });

  it("offers no quota release for other conflicts", async () => {
    const user = userEvent.setup();
    setUser(["printing:read", "printing:admin"]);
    mockApi({ status: "failed" });
    (api.patch as any).mockRejectedValueOnce({ response: { status: 409, data: { message: "Invalid print job transition: failed -> queued" } } });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Einreihen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Trotz Kontingent freigeben" })).not.toBeInTheDocument();
  });
});
