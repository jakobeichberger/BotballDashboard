import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import AwardsPage from "@/pages/AwardsPage";
import TimeoutCardsPanel from "@/modules/scoring/extras/TimeoutCardsPanel";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() } }));

const AWARDS = {
  event_id: "e1",
  template: "ecer",
  published: false,
  published_at: null,
  awards: [
    {
      id: "a1", key: "botball_overall", label: "Botball – Overall", kind: "computed", source: "overall", team_category: "botball", places: 3, per_course: false,
      nominations: [],
      results: [{ team_id: "t1", team_name: "TechSupport", team_number: "26-0603", place: 1, course: null, score: 2.813288941, note: null }],
    },
    {
      id: "a2", key: "spirit_of_ecer", label: "Spirit of ECER", kind: "judged", source: null, team_category: null, places: 1, per_course: false,
      nominations: [{ id: "n1", team_id: "t2", team_name: "ByteMe", note: "Helped everyone" }],
      results: [],
    },
  ],
};

function mockApi() {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/awards/events/e1") return Promise.resolve({ data: AWARDS });
    if (url.endsWith("/registrations")) return Promise.resolve({ data: [{ team_id: "t1", team_name: "TechSupport", team_number: "26-0603" }, { team_id: "t2", team_name: "ByteMe", team_number: "26-0188" }] });
    if (url.endsWith("/timeouts")) return Promise.resolve({ data: [{ id: "c1", team_id: "t2", team_name: "ByteMe", round_number: 2, reason: "before_hands_off", note: null, used_at: "2026-04-10T10:00:00Z" }] });
    return Promise.resolve({ data: [] });
  });
  (api.post as any).mockResolvedValue({ data: {} });
  (api.put as any).mockResolvedValue({ data: {} });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/events/e1/awards"]}>
        <Routes><Route path="/events/:eventId/awards" element={<AwardsPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AwardsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ hasPermission: (permission: string) => ["scoring:read", "scoring:write", "scoring:admin"].includes(permission) } as any);
  });

  it("shows computed results and lets the jury decide a judged award", async () => {
    mockApi();
    renderPage();
    const overall = await screen.findByRole("region", { name: "Botball – Overall" });
    expect(within(overall).getByText(/TechSupport/)).toBeInTheDocument();
    const spirit = screen.getByRole("region", { name: "Spirit of ECER" });
    fireEvent.change(within(spirit).getByLabelText("Platz für ByteMe"), { target: { value: "1" } });
    fireEvent.click(within(spirit).getByRole("button", { name: "Entscheidung speichern" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/awards/a2/results", { placements: [{ team_id: "t2", place: 1 }] }));
  });

  it("applies a template, computes and publishes", async () => {
    mockApi();
    renderPage();
    await screen.findByRole("region", { name: "Spirit of ECER" });
    fireEvent.click(screen.getByRole("button", { name: /GCER-Awards anlegen/ }));
    fireEvent.click(screen.getByRole("button", { name: /Aus Ranglisten berechnen/ }));
    fireEvent.click(screen.getByRole("button", { name: /Veröffentlichen/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/awards/events/e1/publish", { published: true }));
    expect(api.post).toHaveBeenCalledWith("/awards/events/e1/templates/gcer");
    expect(api.post).toHaveBeenCalledWith("/awards/events/e1/compute");
  });
});

describe("TimeoutCardsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ hasPermission: () => true } as any);
  });

  it("lists used cards and only offers teams that still have theirs", async () => {
    mockApi();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <TimeoutCardsPanel eventId="e1" registrations={[{ team_id: "t1", team_name: "TechSupport" }, { team_id: "t2", team_name: "ByteMe" }] as any} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/ByteMe · Runde 2/)).toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "Team mit Timeout" });
    expect(within(select).queryByRole("option", { name: "ByteMe" })).not.toBeInTheDocument();
    fireEvent.change(select, { target: { value: "t1" } });
    fireEvent.click(screen.getByRole("button", { name: "Timeout erfassen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/scoring/events/e1/timeouts", { team_id: "t1", round_number: null, reason: "before_hands_off" }));
  });
});
