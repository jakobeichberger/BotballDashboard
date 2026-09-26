import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import EventSchedulePage from "@/pages/EventSchedulePage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { BracketPhase, EventPhase, ScheduledMatch } from "@/api/types";

// Event-day path without tests before (review 2026-09, #5): generating the
// schedule, rescheduling a match and entering DE winners.
vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));

const get = api.get as ReturnType<typeof vi.fn>;
const post = api.post as ReturnType<typeof vi.fn>;
const patch = api.patch as ReturnType<typeof vi.fn>;

const PHASES: EventPhase[] = [
  { id: "p1", event_id: "e1", name: "Seeding", phase_type: "seeding", sort_order: 0, status: "draft", rounds: 3, starts_at: null, ends_at: null, settings: {} },
  { id: "p2", event_id: "e1", name: "DE", phase_type: "double_elimination", sort_order: 1, status: "live", rounds: 1, starts_at: null, ends_at: null, settings: {} },
];

function participant(position: number, teamId: string | null, name: string | null, result: string | null = null) {
  return { id: `pp-${position}-${teamId}`, team_id: teamId, team_name: name, team_number: null, position, side: position === 1 ? "left" : "right", result };
}

function match(overrides: Partial<ScheduledMatch>): ScheduledMatch {
  return {
    id: "m1", event_id: "e1", phase_id: "p1", code: "1-S1", round_number: 1, sequence_number: 1,
    table_number: 1, scheduled_at: "2026-07-18T08:00:00Z", duration_minutes: 10, status: "scheduled",
    bracket: "seeding", version: 3, participants: [participant(1, "t1", "Alpha")], ...overrides,
  };
}

const SCHEDULE = [match({}), match({ id: "m2", code: "1-S2", table_number: 2, participants: [participant(1, "t2", "Beta")] })];
const DE_MATCH = match({
  id: "d1", phase_id: "p2", code: "2-W1", bracket: "winner", version: 5,
  participants: [participant(1, "t1", "Alpha"), participant(2, "t2", "Beta")],
});
const BRACKET: BracketPhase[] = [
  { phase_id: "p2", phase_name: "DE", phase_type: "double_elimination", status: "live", bracket_label: "botball", matches: [DE_MATCH], placements: [] },
];

function mockApi({ schedule = SCHEDULE, bracket = BRACKET }: { schedule?: ScheduledMatch[]; bracket?: BracketPhase[] } = {}) {
  get.mockImplementation((url: string) => {
    if (url.endsWith("/phases")) return Promise.resolve({ data: PHASES });
    if (url.endsWith("/schedule")) return Promise.resolve({ data: schedule });
    if (url.endsWith("/bracket")) return Promise.resolve({ data: bracket });
    return Promise.resolve({ data: [] });
  });
}

function login(permissions: string[]) {
  useAuthStore.setState({
    accessToken: "tok",
    user: { id: "u1", display_name: "Leitung", is_superuser: false, roles: [], permissions } as never,
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/events/e1/schedule"]}>
        <Routes>
          <Route path="/events/:eventId/schedule" element={<EventSchedulePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventSchedulePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
    post.mockResolvedValue({ data: [] });
    patch.mockResolvedValue({ data: {} });
  });

  it("generates the schedule of the chosen phase from the local start time", async () => {
    login(["events:admin", "events:write"]);
    renderPage();
    const phase = await screen.findByRole("combobox", { name: "Turnierphase" });
    await waitFor(() => expect(within(phase).getAllByRole("option")).toHaveLength(3));
    fireEvent.change(phase, { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Startzeit"), { target: { value: "2026-07-18T09:30" } });
    fireEvent.click(screen.getByRole("button", { name: "Generieren" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/v1/events/e1/schedule/generate", {
        phase_id: "p1",
        // datetime-local is local time; the API gets the instant in UTC.
        starts_at: new Date("2026-07-18T09:30").toISOString(),
        slot_minutes: 10,
      }),
    );
  });

  it("shows why generating failed", async () => {
    login(["events:admin", "events:write"]);
    post.mockRejectedValue({ response: { status: 409, data: { code: "http_409", message: "Phase already has a schedule" } } });
    renderPage();
    const phase = await screen.findByRole("combobox", { name: "Turnierphase" });
    await waitFor(() => expect(within(phase).getAllByRole("option")).toHaveLength(3));
    fireEvent.change(phase, { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Startzeit"), { target: { value: "2026-07-18T09:30" } });
    fireEvent.click(screen.getByRole("button", { name: "Generieren" }));
    expect(await screen.findByRole("alert")).not.toBeEmptyDOMElement();
  });

  it("reschedules a match with its version and saves only changed matches", async () => {
    login(["events:write"]);
    renderPage();
    const save = await screen.findAllByRole("button", { name: "Speichern" });
    // Nothing edited yet: nothing to save.
    save.forEach((button) => expect(button).toBeDisabled());
    fireEvent.change(screen.getByLabelText("Tisch 1-S1"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Zeit 1-S1"), { target: { value: "2026-07-18T11:15" } });
    fireEvent.change(screen.getByLabelText("Status 1-S1"), { target: { value: "called" } });
    expect(save[0]).toBeEnabled();
    expect(save[1]).toBeDisabled();
    fireEvent.click(save[0]);
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith("/v1/events/e1/schedule/m1", {
        table_number: 2,
        scheduled_at: new Date("2026-07-18T11:15").toISOString(),
        status: "called",
        expected_version: 3,
      }),
    );
    // Saved: the edit is dropped and the button disabled again.
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Speichern" })[0]).toBeDisabled());
  });

  it("keeps the edit and shows the conflict when the slot is taken", async () => {
    login(["events:write"]);
    patch.mockRejectedValue({
      response: { status: 409, data: { code: "http_409", message: "Another match already uses this table and time slot" } },
    });
    renderPage();
    fireEvent.change(await screen.findByLabelText("Tisch 1-S2"), { target: { value: "1" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Speichern" })[1]);
    await waitFor(() => expect(patch).toHaveBeenCalled());
    // Without events:admin the error shows next to the bracket.
    expect(await screen.findByRole("alert")).not.toBeEmptyDOMElement();
    expect((screen.getByLabelText("Tisch 1-S2") as HTMLInputElement).value).toBe("1");
    expect(screen.getAllByRole("button", { name: "Speichern" })[1]).toBeEnabled();
  });

  it("enters a DE winner with the match version", async () => {
    login(["events:write", "scoring:admin"]);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Beta gewinnt 2-W1" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/v1/events/e1/schedule/d1/result", {
        winner_team_id: "t2",
        expected_version: 5,
      }),
    );
  });

  it("is read-only without write permissions", async () => {
    login(["events:read"]);
    renderPage();
    expect(await screen.findByText("1-S1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generieren" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Zeit 1-S1")).not.toBeInTheDocument();
    // No winner buttons without scoring:admin.
    expect(screen.queryByRole("button", { name: /gewinnt/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("geplant").length).toBeGreaterThan(0);
  });

  it("takes the seeds from the seeding ranking", async () => {
    login(["events:admin", "events:write"]);
    post.mockResolvedValue({ data: [{}, {}, {}] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Seeds aus Seeding/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/v1/events/e1/registrations/seeds-from-seeding", {}));
    expect(await screen.findByRole("status")).toHaveTextContent("3 Teams");
  });

  it("says so when there is no schedule yet", async () => {
    login(["events:read"]);
    mockApi({ schedule: [], bracket: [] });
    renderPage();
    expect(await screen.findByText("Noch kein Zeitplan vorhanden.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Brackets" })).not.toBeInTheDocument();
  });
});
