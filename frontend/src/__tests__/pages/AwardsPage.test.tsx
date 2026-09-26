import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import AwardsPage from "@/pages/AwardsPage";
import TimeoutCardsPanel from "@/modules/scoring/extras/TimeoutCardsPanel";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { confirmAction } from "@/lib/confirm";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
vi.mock("@/lib/confirm", () => ({ confirmAction: vi.fn(async () => true) }));

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

function mockApi(awards: unknown = AWARDS) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/awards/events/e1") return Promise.resolve({ data: awards });
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
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/awards/a2/results", { placements: [{ team_id: "t2", place: 1 }], replace: false }));
    // A first decision needs no confirmation.
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it("prefills the places from the decision and never sends an empty list by accident", async () => {
    const decided: any = structuredClone(AWARDS);
    decided.awards[1].results = [{ team_id: "t2", team_name: "ByteMe", team_number: "26-0188", place: 1, course: null, score: null, note: null }];
    mockApi(decided);
    renderPage();
    const spirit = await screen.findByRole("region", { name: "Spirit of ECER" });
    const select = within(spirit).getByLabelText("Platz für ByteMe") as HTMLSelectElement;
    expect(select.value).toBe("1");
    const save = within(spirit).getByRole("button", { name: "Entscheidung speichern" });
    // Unchanged decision: nothing to save.
    expect(save).toBeDisabled();
    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(save);
    await waitFor(() => expect(confirmAction).toHaveBeenCalled());
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/awards/a2/results", { placements: [], replace: true }));
  });

  it("keeps the decision when the jury cancels the replacement", async () => {
    const decided: any = structuredClone(AWARDS);
    decided.awards[1].places = 2;
    decided.awards[1].results = [{ team_id: "t2", team_name: "ByteMe", team_number: "26-0188", place: 1, course: null, score: null, note: null }];
    mockApi(decided);
    (confirmAction as any).mockResolvedValueOnce(false);
    renderPage();
    const spirit = await screen.findByRole("region", { name: "Spirit of ECER" });
    fireEvent.change(within(spirit).getByLabelText("Platz für ByteMe"), { target: { value: "2" } });
    fireEvent.click(within(spirit).getByRole("button", { name: "Entscheidung speichern" }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalled());
    expect(api.put).not.toHaveBeenCalled();
  });

  it("shows an error with retry instead of an empty page when loading fails", async () => {
    mockApi();
    (api.get as any).mockImplementation((url: string) => (url === "/awards/events/e1" ? Promise.reject({ response: { status: 500, data: {} } }) : Promise.resolve({ data: [] })));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Daten konnten nicht geladen werden.");
    expect(screen.getByRole("button", { name: /Erneut versuchen/ })).toBeInTheDocument();
  });

  it("asks before withdrawing a nomination", async () => {
    mockApi();
    (confirmAction as any).mockResolvedValueOnce(false);
    renderPage();
    const spirit = await screen.findByRole("region", { name: "Spirit of ECER" });
    fireEvent.click(within(spirit).getByRole("button", { name: /Nominierung von ByteMe zurückziehen/ }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalled());
    expect(api.delete).not.toHaveBeenCalled();
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
