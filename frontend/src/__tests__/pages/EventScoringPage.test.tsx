import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import EventScoringPage from "@/pages/EventScoringPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
  isQueuedResponse: (data: { queued?: boolean } | null) => !!data?.queued,
}));

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, options?: Record<string, unknown>) =>
        options ? `${key} ${Object.values(options).join("/")}` : key,
    }),
  };
});

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

function renderPage() {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
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
    const next = await screen.findByRole("button", { name: "nextMatch" });
    await waitFor(() => expect(screen.getAllByRole("option", { name: /S-1/ }).length).toBeGreaterThan(0));
    fireEvent.click(next);
    expect(within(screen.getByRole("navigation")).getByText(/^S-1 ·/)).toBeInTheDocument();
    expect(screen.getByText("matchPosition 1/2")).toBeInTheDocument();
    expect((screen.getByLabelText("team") as HTMLSelectElement).value).toBe("t1");

    fireEvent.click(next);
    expect(within(screen.getByRole("navigation")).getByText(/^S-2 ·/)).toBeInTheDocument();
    expect((screen.getByLabelText("team") as HTMLSelectElement).value).toBe("t2");
    expect(screen.getByRole("button", { name: "nextMatch" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "previousMatch" }));
    expect(within(screen.getByRole("navigation")).getByText(/^S-1 ·/)).toBeInTheDocument();
  });

  it("switches matches with a horizontal swipe", async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getAllByRole("option", { name: /S-2/ }).length).toBeGreaterThan(0));
    const page = container.firstElementChild as HTMLElement;
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

  it("asks for confirmation with a summary before the official submit", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { id: "m1" } });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "nextMatch" }));
    await waitFor(() => expect((screen.getByLabelText("team") as HTMLSelectElement).value).toBe("t1"));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "4" } });
    // The first checkbox is the sheet field "Geparkt"; the special-rule flags follow it.
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: /reviewScore/ }));

    const dialog = await screen.findByRole("dialog");
    expect(api.post).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Alpha (A-1)")).toBeInTheDocument();
    expect(within(dialog).getByText("Würfel")).toBeInTheDocument();
    expect(within(dialog).getByText("Ja")).toBeInTheDocument();
    expect(within(dialog).getByTestId("confirm-total")).toHaveTextContent("13.00");

    fireEvent.click(within(dialog).getByRole("button", { name: "Verbindlich absenden" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [url, body, config] = (api.post as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`/v1/events/${EVENT}/matches`);
    expect(body).toMatchObject({ team_id: "t1", scheduled_match_id: "sm1", raw_scores: { cubes: 4, parked: true } });
    expect(body.idempotency_key).toEqual(expect.any(String));
    expect(config.offlineLabel).toContain("Alpha");
    expect(await screen.findByText("scoreSaved")).toBeInTheDocument();
  });

  it("lets the juror go back and correct instead of submitting", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "nextMatch" }));
    await waitFor(() => expect((screen.getByLabelText("team") as HTMLSelectElement).value).toBe("t1"));
    fireEvent.click(screen.getByRole("button", { name: /reviewScore/ }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Korrigieren" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("stays usable offline and reports a queued entry", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 202, data: { queued: true, idempotency_key: "k" } });
    renderPage();
    expect(await screen.findByText("offlineScoring")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "nextMatch" }));
    await waitFor(() => expect((screen.getByLabelText("team") as HTMLSelectElement).value).toBe("t1"));
    expect(screen.getByRole("spinbutton")).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /reviewScore/ }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Lokal speichern" }));
    expect(await screen.findByText("scoreQueued")).toBeInTheDocument();
  });
});
