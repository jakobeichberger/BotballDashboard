/**
 * Pages that used to render a failed load as empty data (no teams, KPIs 0,
 * empty formula list) show an error with retry instead; failed saves say so.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { ReactElement } from "react";
import AerialPage from "@/pages/AerialPage";
import JBCPage from "@/pages/JBCPage";
import FormulasPage from "@/pages/FormulasPage";
import AdminDashboard from "@/pages/dashboard/AdminDashboard";
import { api } from "@/lib/api";
import { useToastStore } from "@/lib/toast";
import { confirmAction } from "@/lib/confirm";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
vi.mock("@/lib/confirm", () => ({ confirmAction: vi.fn(async () => false) }));

const SEASON = { id: "s1", year: 2026, use_aerial: true, active_categories: ["botball", "aerial_junior", "jbc"] };
const FAIL = { response: { status: 500, data: {} } };

function mockApi(failing: string[] = [], extra: Record<string, unknown> = {}) {
  (api.get as any).mockImplementation((url: string) => {
    if (failing.some((part) => url.includes(part))) return Promise.reject(FAIL);
    if (url === "/v1/events/e2") return Promise.resolve({ data: { id: "e2", season_id: "s1", name: "ECER" } });
    if (url === "/seasons/s1") return Promise.resolve({ data: SEASON });
    for (const [key, value] of Object.entries(extra)) if (url.includes(key)) return Promise.resolve({ data: value });
    return Promise.resolve({ data: [] });
  });
}

function renderAt(path: string, element: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/events/e2${path}`]}>
        <Routes><Route path={`/events/:eventId${path}`} element={element} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useToastStore.setState({ toasts: [] });
});

describe("AerialPage", () => {
  it("shows a load error instead of teams without runs and zero KPIs", async () => {
    mockApi(["/aerial-results"], { "/teams": [{ id: "t1", name: "Drone Masters", team_number: "AE-1" }] });
    renderAt("/scoring/aerial", <AerialPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Daten konnten nicht geladen werden.");
    expect(screen.queryByRole("list", { name: "Aerial im Überblick" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("reports a failed save", async () => {
    mockApi([], {
      "/teams": [{ id: "t1", name: "Drone Masters", team_number: "AE-1" }],
      "/registrations": [{ team_id: "t1", category: "aerial_junior" }],
    });
    (api.put as any).mockRejectedValue(FAIL);
    renderAt("/scoring/aerial", <AerialPage />);
    fireEvent.change(await screen.findByLabelText(/Drone Masters/, { selector: "input[aria-label*='1']" }), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: /Speichern/ }));
    await waitFor(() => expect(useToastStore.getState().toasts.some((toast) => toast.tone === "error")).toBe(true));
    // The draft is kept so nothing typed is lost.
    expect(screen.getByDisplayValue("50")).toBeInTheDocument();
  });
});

describe("JBCPage", () => {
  it("shows a load error instead of empty points", async () => {
    mockApi(["/jbc-results"]);
    renderAt("/scoring/jbc", <JBCPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Daten konnten nicht geladen werden.");
    expect(screen.queryByRole("list", { name: /JBC/ })).not.toBeInTheDocument();
  });
});

describe("FormulasPage", () => {
  it("shows a load error and offers no reset of a list it could not load", async () => {
    mockApi(["/effective"]);
    renderAt("/formulas", <FormulasPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Daten konnten nicht geladen werden.");
    expect(screen.getByRole("button", { name: /Standard/ })).toBeDisabled();
  });

  it("shows a load error when the event cannot be loaded (instead of loading forever)", async () => {
    mockApi(["/v1/events/e2"]);
    renderAt("/formulas", <FormulasPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Daten konnten nicht geladen werden.");
  });

  it("asks before resetting the formulas to the default", async () => {
    mockApi([], { "/effective": [{ key: "overall", expression: "1" }] });
    renderAt("/formulas", <FormulasPage />);
    await screen.findByDisplayValue("overall");
    fireEvent.click(screen.getByRole("button", { name: /Standard/ }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalled());
    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining("/reset"));
  });
});

describe("AdminDashboard KPIs", () => {
  it("shows a dash, not 0, while the numbers are unknown", () => {
    render(<MemoryRouter><AdminDashboard season={{}} announcements={[]} /></MemoryRouter>);
    const kpis = screen.getByRole("list", { name: "System-Kennzahlen" });
    expect(within(kpis).queryByText("0")).not.toBeInTheDocument();
    expect(within(kpis).getAllByText("–").length).toBeGreaterThan(0);
  });

  it("shows the load error of the numbers", () => {
    const stats = { isError: true, error: FAIL, isFetching: false, refetch: vi.fn() };
    render(<MemoryRouter><AdminDashboard season={{}} announcements={[]} statsQuery={stats} /></MemoryRouter>);
    expect(screen.getByRole("alert")).toHaveTextContent("Daten konnten nicht geladen werden.");
  });
});
