import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import EventScoringPage from "@/pages/EventScoringPage";
import ConfirmHost from "@/components/ConfirmHost";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
  isQueuedResponse: (data: { queued?: boolean } | null) => !!data?.queued,
}));

const EVENT = "ev-1";
const registrations = [
  { id: "r1", team_id: "t1", team_name: "Alpha", team_number: "A-1", seed_number: 1 },
  { id: "r2", team_id: "t2", team_name: "Beta", team_number: null, seed_number: 2 },
];
const schedule = [
  { id: "sm2", code: "S-2", sequence_number: 2, table_number: 1, scheduled_at: "2026-05-01T10:10:00Z", status: "scheduled", participants: [{ team_id: "t2", position: 1 }] },
  { id: "sm1", code: "S-1", sequence_number: 1, table_number: 2, scheduled_at: "2026-05-01T10:00:00Z", status: "scheduled", participants: [{ team_id: "t1", position: 1 }] },
  { id: "sm0", code: "X", sequence_number: 0, table_number: 1, scheduled_at: null, status: "cancelled", participants: [] },
];
const schema = {
  id: "sch",
  fields: [
    { key: "cubes", label: "Würfel", type: "count", multiplier: 2, min_value: 0, max_value: null, required: false },
    { key: "parked", label: "Geparkt", type: "boolean", multiplier: 5, min_value: null, max_value: null, required: false },
  ],
};

function renderPage(overrides: Record<string, unknown> = {}) {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url in overrides) return Promise.resolve({ data: overrides[url] });
    if (url.endsWith("/registrations")) return Promise.resolve({ data: registrations });
    if (url.endsWith("/schedule")) return Promise.resolve({ data: schedule });
    if (url.endsWith("/scoring-schema")) return Promise.resolve({ data: schema });
    if (url === `/v1/events/${EVENT}`) return Promise.resolve({ data: { id: EVENT, season_id: "s1", name: "Regional" } });
    if (url.endsWith("/rules")) return Promise.resolve({ data: { tiebreakers: [], end_contact_bonus_percent: 25 } });
    if (url.endsWith("/outcome")) return Promise.resolve({ data: { reason: "incomplete", winner: null, replay: false, decided_by: null, sides: [] } });
    return Promise.resolve({ data: [] });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/events/${EVENT}/scoring`]}>
        <Routes>
          <Route path="/events/:eventId/scoring" element={<EventScoringPage />} />
        </Routes>
        <ConfirmHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventScoringPage (mobile scoring)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    useAuthStore.setState({
      accessToken: "tok",
      user: { id: "juror", display_name: "Juror", is_superuser: true, roles: [] } as never,
    });
  });

  it("steps through the scheduled matches in play order and preselects the team", async () => {
    renderPage();
    const next = await screen.findByRole("button", { name: "Nächstes Match" });
    await waitFor(() => expect(screen.getAllByRole("option", { name: /S-1/ }).length).toBeGreaterThan(0));
    fireEvent.click(next);
    expect(within(screen.getByRole("navigation")).getByText(/^S-1 ·/)).toBeInTheDocument();
    expect(screen.getByText("Match 1 von 2")).toBeInTheDocument();
    expect((screen.getByLabelText("Team") as HTMLSelectElement).value).toBe("t1");

    fireEvent.click(next);
    expect(within(screen.getByRole("navigation")).getByText(/^S-2 ·/)).toBeInTheDocument();
    expect((screen.getByLabelText("Team") as HTMLSelectElement).value).toBe("t2");
    expect(screen.getByRole("button", { name: "Nächstes Match" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Vorheriges Match" }));
    expect(within(screen.getByRole("navigation")).getByText(/^S-1 ·/)).toBeInTheDocument();
  });

  it("switches matches with a horizontal swipe on the match bar", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByRole("option", { name: /S-2/ }).length).toBeGreaterThan(0));
    const page = screen.getByRole("navigation");
    fireEvent.touchStart(page, { touches: [{ clientX: 300, clientY: 100 }] });
    fireEvent.touchEnd(page, { changedTouches: [{ clientX: 100, clientY: 110 }] });
    expect(within(screen.getByRole("navigation")).getByText(/^S-1 ·/)).toBeInTheDocument();
    fireEvent.touchStart(page, { touches: [{ clientX: 300, clientY: 100 }] });
    fireEvent.touchEnd(page, { changedTouches: [{ clientX: 100, clientY: 105 }] });
    expect(within(screen.getByRole("navigation")).getByText(/^S-2 ·/)).toBeInTheDocument();
    // A mostly vertical gesture is a scroll, not a swipe.
    fireEvent.touchStart(page, { touches: [{ clientX: 100, clientY: 100 }] });
    fireEvent.touchEnd(page, { changedTouches: [{ clientX: 200, clientY: 400 }] });
    expect(within(screen.getByRole("navigation")).getByText(/^S-2 ·/)).toBeInTheDocument();
  });

  it("ignores swipes on the score form", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Nächstes Match" }));
    const input = screen.getByRole("spinbutton");
    fireEvent.touchStart(input, { touches: [{ clientX: 300, clientY: 100 }] });
    fireEvent.touchEnd(input, { changedTouches: [{ clientX: 100, clientY: 100 }] });
    expect(within(screen.getByRole("navigation")).getByText(/^S-1 ·/)).toBeInTheDocument();
  });

  it("asks before switching matches would discard entered values", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Nächstes Match" }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "4" } });

    // Cancel: stay on the match, keep the value.
    fireEvent.click(screen.getByRole("button", { name: "Nächstes Match" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(within(screen.getByRole("navigation")).getByText(/^S-1 ·/)).toBeInTheDocument();
    expect(screen.getByRole("spinbutton")).toHaveValue(4);

    // Confirm: switch and start empty.
    fireEvent.click(screen.getByRole("button", { name: "Nächstes Match" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Verwerfen" }));
    await waitFor(() => expect(within(screen.getByRole("navigation")).getByText(/^S-2 ·/)).toBeInTheDocument());
    expect(screen.getByRole("spinbutton")).toHaveValue(null);
  });

  it("tells a missing schema apart from a failed load", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) =>
      url.endsWith("/scoring-schema") ? Promise.reject({ response: { status: 500, data: {} } }) : Promise.resolve({ data: [] }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/events/ev-2/scoring"]}>
          <Routes><Route path="/events/:eventId/scoring" element={<EventScoringPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/Serverfehler/);
    expect(screen.getByRole("button", { name: "Erneut versuchen" })).toBeInTheDocument();
  });

  it("asks for confirmation with a summary before the official submit", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { id: "m1" } });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Nächstes Match" }));
    await waitFor(() => expect((screen.getByLabelText("Team") as HTMLSelectElement).value).toBe("t1"));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "4" } });
    // The first checkbox is the sheet field "Geparkt"; the special-rule flags follow it.
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: /Prüfen & absenden/ }));

    const dialog = await screen.findByRole("dialog");
    expect(api.post).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Alpha (A-1)")).toBeInTheDocument();
    expect(within(dialog).getByText("Würfel")).toBeInTheDocument();
    expect(within(dialog).getByText("Ja")).toBeInTheDocument();
    expect(within(dialog).getByTestId("confirm-total")).toHaveTextContent("13,00");

    fireEvent.click(within(dialog).getByRole("button", { name: "Verbindlich absenden" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [url, body, config] = (api.post as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`/v1/events/${EVENT}/matches`);
    expect(body).toMatchObject({ team_id: "t1", scheduled_match_id: "sm1", raw_scores: { cubes: 4, parked: true } });
    expect(body.idempotency_key).toEqual(expect.any(String));
    expect(config.offlineLabel).toContain("Alpha");
    // The confirmation names team and points and sits in the sticky bar next to the button.
    const saved = await screen.findByText(/^Offiziell gespeichert: Alpha \(A-1\) · 13/);
    expect(saved.closest(".sticky")).not.toBeNull();
  });

  it("lets the juror go back and correct instead of submitting", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Nächstes Match" }));
    await waitFor(() => expect((screen.getByLabelText("Team") as HTMLSelectElement).value).toBe("t1"));
    fireEvent.click(screen.getByRole("button", { name: /Prüfen & absenden/ }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Korrigieren" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("stays usable offline and reports a queued entry", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 202, data: { queued: true, idempotency_key: "k" } });
    renderPage();
    expect(await screen.findByText("Offline: Wertungen werden auf diesem Gerät gespeichert und automatisch synchronisiert, sobald wieder eine Verbindung besteht.")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Nächstes Match" }));
    await waitFor(() => expect((screen.getByLabelText("Team") as HTMLSelectElement).value).toBe("t1"));
    expect(screen.getByRole("spinbutton")).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Prüfen & absenden/ }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Lokal speichern" }));
    expect(await screen.findByText("Offline gespeichert – wird synchronisiert, sobald eine Verbindung besteht.")).toBeInTheDocument();
  });

  it("does not offer Aerial or JBC teams", async () => {
    renderPage({
      [`/v1/events/${EVENT}/registrations`]: [
        ...registrations.map((item) => ({ ...item, category: "botball" })),
        { id: "r3", team_id: "t3", team_name: "Drone Masters", team_number: null, seed_number: null, category: "aerial_junior" },
        { id: "r4", team_id: "t4", team_name: "Code Cubs", team_number: null, seed_number: null, category: "jbc" },
      ],
    });
    const select = await screen.findByLabelText("Team");
    await within(select).findByRole("option", { name: /Alpha/ });
    expect(within(select).queryByRole("option", { name: /Drone Masters/ })).not.toBeInTheDocument();
    expect(within(select).queryByRole("option", { name: /Code Cubs/ })).not.toBeInTheDocument();
  });

  it("blocks a second score for a scheduled seeding match that is already scored", async () => {
    renderPage({ [`/v1/events/${EVENT}/matches`]: [{ id: "m1", scheduled_match_id: "sm1", is_practice: false, total_score: 42 }] });
    fireEvent.click(await screen.findByRole("button", { name: "Nächstes Match" }));
    await waitFor(() => expect((screen.getByLabelText("Team") as HTMLSelectElement).value).toBe("t1"));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(`/v1/events/${EVENT}/matches`, { params: { team_id: "t1" } }));
    fireEvent.click(screen.getByRole("button", { name: /Prüfen & absenden/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Für Alpha \(A-1\) ist in diesem Match schon eine Wertung erfasst \(42[,0]* P\.\)/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "So nicht absendbar" })).toBeDisabled();
  });

  it("gives the special-rule checkboxes a 44 px tap target", async () => {
    renderPage();
    const roundLost = await screen.findByRole("checkbox", { name: /^Runde verloren/ });
    expect(roundLost.closest("label")).toHaveClass("min-h-11");
    expect(roundLost).toHaveClass("h-6", "w-6");
  });
});
