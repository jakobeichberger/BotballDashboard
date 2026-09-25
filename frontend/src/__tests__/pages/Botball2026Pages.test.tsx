import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactElement } from "react";
import AerialPage from "@/pages/AerialPage";
import JBCPage from "@/pages/JBCPage";
import CategoryRegistryEditor from "@/components/seasons/CategoryRegistryEditor";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), patch: vi.fn() } }));

const SEASON = { id: "s1", year: 2026, use_aerial: true, active_categories: ["botball", "aerial_junior", "jbc"] };

function mockApi(extra: Record<string, unknown> = {}) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/v1/events/e2") return Promise.resolve({ data: { id: "e2", season_id: "s1" } });
    if (url === "/seasons/s1") return Promise.resolve({ data: SEASON });
    for (const [key, value] of Object.entries(extra)) {
      if (url.includes(key)) return Promise.resolve({ data: value });
    }
    return Promise.resolve({ data: [] });
  });
  (api.put as any).mockResolvedValue({ data: [] });
}

function renderAt(path: string, element: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/events/e2${path}`]}>
        <Routes>
          <Route path={`/events/:eventId${path}`} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AerialPage with a run list", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the category's runs and previews the best three", async () => {
    mockApi({
      "/teams": [{ id: "t1", name: "Drone Masters", team_number: "AE-0013" }, { id: "t2", name: "Senior", team_number: null }],
      "/registrations": [{ team_id: "t1", category: "aerial_junior" }, { team_id: "t2", category: "aerial" }],
      "/aerial-results": [{ team_id: "t1", runs: [70, 52.5, 115, 30, 60, 105] }],
    });
    renderAt("/scoring/aerial", <AerialPage />);
    expect(await screen.findByText("Drone Masters")).toBeInTheDocument();
    // Aerial Junior: six runs, the senior team is not listed in this view.
    expect(screen.getAllByRole("columnheader", { name: /run \d/i })).toHaveLength(6);
    expect(screen.queryByText("Senior")).not.toBeInTheDocument();
    // (115 + 105 + 70) / 3, as in the ECER 2026 results
    expect(screen.getByText("96,67")).toBeInTheDocument();
  });

  it("saves the runs as a list", async () => {
    mockApi({
      "/teams": [{ id: "t1", name: "Drone Masters", team_number: null }],
      "/registrations": [{ team_id: "t1", category: "aerial_junior" }],
    });
    renderAt("/scoring/aerial", <AerialPage />);
    fireEvent.change(await screen.findByLabelText(/run 2 für drone masters/i), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect((api.put as any).mock.calls[0]).toEqual(["/scoring/events/e2/aerial-results", [{ team_id: "t1", runs: [null, 40] }]]);
  });
});

describe("JBCPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists the JBC teams with points and rank and saves changes", async () => {
    mockApi({
      "/registrations": [
        { team_id: "j1", team_name: "BEst SIlent CHaos", team_number: "JBC-009", category: "jbc" },
        { team_id: "b1", team_name: "Botball team", team_number: null, category: "botball" },
      ],
      "/jbc-results": [{ team_id: "j1", points: 21, challenges: [], rank: 1 }],
    });
    renderAt("/scoring/jbc", <JBCPage />);
    const input = await screen.findByLabelText(/punkte für best silent chaos/i);
    expect(input).toHaveValue(21);
    expect(screen.queryByText("Botball team")).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: "22" } });
    fireEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/scoring/events/e2/jbc-results", [{ team_id: "j1", points: 22 }]));
  });
});

describe("CategoryRegistryEditor", () => {
  beforeEach(() => vi.clearAllMocks());

  it("edits the registry and saves it in order", async () => {
    mockApi({ "/scoring/formulas/reference": { presets: [{ id: "aerial_2026", label: "Aerial 2026", category: "aerial" }] } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CategoryRegistryEditor seasonId="s1" /></QueryClientProvider>);
    const keys = await screen.findAllByRole("textbox", { name: "Schlüssel" });
    expect(keys.map((input) => (input as HTMLInputElement).value)).toEqual(["botball", "open", "aerial_junior", "aerial", "jbc"]);

    fireEvent.click(screen.getByRole("button", { name: /kategorie hinzufügen/i }));
    const rows = screen.getAllByRole("row");
    const last = rows[rows.length - 1];
    fireEvent.change(within(last).getByRole("textbox", { name: "Schlüssel" }), { target: { value: "rookies" } });
    fireEvent.change(within(last).getByRole("textbox", { name: "Bezeichnung (DE)" }), { target: { value: "Neulinge" } });
    fireEvent.change(within(last).getByRole("textbox", { name: "Bezeichnung (EN)" }), { target: { value: "Rookies" } });
    fireEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = (api.put as any).mock.calls[0];
    expect(url).toBe("/seasons/s1/categories");
    expect(body.map((entry: { key: string; sort_order: number }) => [entry.key, entry.sort_order])).toEqual([
      ["botball", 0], ["open", 1], ["aerial_junior", 2], ["aerial", 3], ["jbc", 4], ["rookies", 5],
    ]);
  });

  it("blocks saving an invalid key", async () => {
    mockApi();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CategoryRegistryEditor seasonId="s1" /></QueryClientProvider>);
    const [first] = await screen.findAllByRole("textbox", { name: "Schlüssel" });
    fireEvent.change(first, { target: { value: "Bad Key" } });
    expect(screen.getByRole("button", { name: /speichern/i })).toBeDisabled();
  });
});
