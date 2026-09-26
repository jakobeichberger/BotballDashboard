import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import type { ReactNode } from "react";
import ScoreEntryPage from "@/pages/ScoreEntryPage";
import PartsChallengePanel from "@/modules/scoring/extras/PartsChallengePanel";
import { api } from "@/lib/api";
import { confirmAction } from "@/lib/confirm";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration, ScheduledMatch } from "@/api/types";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  isQueuedResponse: (data: { queued?: boolean } | null) => !!data?.queued,
}));

// Destructive actions ask first (lib/confirm); these tests confirm.
vi.mock("@/lib/confirm", () => ({ confirmAction: vi.fn().mockResolvedValue(true) }));

const get = api.get as ReturnType<typeof vi.fn>;

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function asUser(permissions: string[]) {
  useAuthStore.setState({
    user: { id: "u1", display_name: "Jury", is_superuser: false, roles: [], permissions } as never,
  });
}

const match = {
  id: "m1", version: 2, team_id: "t1", round_number: 1, total_score: 30, raw_scores: { cubes: 10 },
  is_practice: false, confirmed_by: null, yellow_card: true, red_card: false, is_disqualified: false,
};

describe("cards and disqualification in the score entry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    get.mockImplementation((url: string) => {
      if (url === "/seasons/active") return Promise.resolve({ data: { id: "s1" } });
      if (url === "/teams") return Promise.resolve({ data: [{ id: "t1", name: "Alpha" }] });
      if (url === "/teams/mine") return Promise.resolve({ data: [{ id: "t1", name: "Alpha" }] });
      if (url === "/scoring/seasons/s1/schema") return Promise.resolve({ data: { fields: [{ key: "cubes", label: "Würfel", multiplier: 3, max_value: null, type: "count" }] } });
      if (url === "/scoring/seasons/s1/matches") return Promise.resolve({ data: [match] });
      return Promise.resolve({ data: [] });
    });
    (api.patch as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { ...match, version: 3 } });
  });

  it("shows the penalties of a run and lets a juror disqualify it with a reason", async () => {
    asUser(["scoring:read", "scoring:write", "scoring:admin"]);
    wrap(<ScoreEntryPage />);
    const row = (await screen.findByText("Gelb")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Karten & Disqualifikation für Alpha, Runde 1" }));

    const dialog = await screen.findByRole("dialog", { name: "Strafen · Alpha · Runde 1" });
    expect(within(dialog).getByRole("checkbox", { name: /Gelbe Karte/ })).toBeChecked();
    const save = within(dialog).getByRole("button", { name: "Entscheidung speichern" });
    expect(save).toBeDisabled(); // nothing changed yet

    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Disqualifikation/ }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Begründung" }), { target: { value: "Roboter hat den Tisch verlassen" } });
    fireEvent.click(save);

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch).toHaveBeenCalledWith("/scoring/matches/m1", {
      yellow_card: true,
      red_card: false,
      is_disqualified: true,
      expected_version: 2,
      correction_reason: "Roboter hat den Tisch verlassen",
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the backend error, e.g. a version conflict", async () => {
    asUser(["scoring:read", "scoring:write", "scoring:admin"]);
    (api.patch as ReturnType<typeof vi.fn>).mockRejectedValue({ response: { status: 409, data: { code: "http_409", message: "Score was changed by another user" } } });
    wrap(<ScoreEntryPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Karten & Disqualifikation für Alpha, Runde 1" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Rote Karte/ }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Begründung" }), { target: { value: "Unsportlich" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Entscheidung speichern" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/Konflikt: Die Daten wurden inzwischen geändert/);
  });

  it("offers no penalty action to mentors", async () => {
    asUser(["scoring:read", "scoring:write"]);
    wrap(<ScoreEntryPage />);
    expect(await screen.findByText("Gelb")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Karten & Disqualifikation/ })).not.toBeInTheDocument();
  });
});

const registrations = [
  { id: "r1", team_id: "t1", team_name: "Alpha" },
  { id: "r2", team_id: "t2", team_name: "Beta" },
  { id: "r3", team_id: "t3", team_name: "Gamma" },
] as EventRegistration[];
const matches = [
  { id: "sm1", code: "DE-1", participants: [{ id: "p1", team_id: "t1" }, { id: "p2", team_id: "t2" }] },
] as unknown as ScheduledMatch[];
const openChallenge = {
  id: "c1", event_id: "e1", scheduled_match_id: "sm1", challenger_team_id: "t1", challenged_team_id: "t2",
  description: "Servo nicht aus dem Kit", upheld: null, ruling_note: null, decided_by: null, decided_at: null,
  created_at: "2026-05-01T10:00:00Z",
};

describe("PartsChallengePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockImplementation((url: string) =>
      Promise.resolve({ data: url === "/scoring/events/e1/parts-challenges" ? [openChallenge, { ...openChallenge, id: "c2", upheld: false, ruling_note: "Teil ist zulässig" }] : [] }),
    );
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
    (api.put as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
    (confirmAction as ReturnType<typeof vi.fn>).mockResolvedValue(true);
  });

  it("lists challenges with their outcome and lets the head judge rule", async () => {
    asUser(["scoring:read", "scoring:admin"]);
    wrap(<PartsChallengePanel eventId="e1" matches={matches} registrations={registrations} />);
    const items = await screen.findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Alpha fordert Beta heraus");
    expect(items[0]).toHaveTextContent("DE-1");
    expect(items[1]).toHaveTextContent("Abgewiesen");
    // Rejected: the challenger loses the match.
    expect(items[1]).toHaveTextContent("Disqualifiziert: Alpha – Teil ist zulässig");

    fireEvent.change(within(items[0]).getByRole("textbox", { name: "Begründung der Entscheidung" }), { target: { value: "Fremdes Servo" } });
    fireEvent.click(within(items[0]).getByRole("button", { name: "Stattgeben" }));
    expect(confirmAction).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining("Beta") }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/scoring/parts-challenges/c1/ruling", { upheld: true, ruling_note: "Fremdes Servo" }));
  });

  it("files a challenge between the participants of a match", async () => {
    asUser(["scoring:read", "scoring:admin"]);
    wrap(<PartsChallengePanel eventId="e1" matches={matches} registrations={registrations} />);
    await screen.findAllByRole("listitem");
    fireEvent.change(screen.getByRole("combobox", { name: "Match" }), { target: { value: "sm1" } });
    const challenger = screen.getByRole("combobox", { name: "Anfechtendes Team" });
    // Gamma does not play DE-1.
    expect(within(challenger).queryByRole("option", { name: "Gamma" })).not.toBeInTheDocument();
    fireEvent.change(challenger, { target: { value: "t2" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Angefochtenes Team" }), { target: { value: "t1" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Beschreibung" }), { target: { value: "Nicht zugelassener Motor" } });
    fireEvent.click(screen.getByRole("button", { name: /Challenge erfassen/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/scoring/events/e1/parts-challenges", {
      scheduled_match_id: "sm1",
      challenger_team_id: "t2",
      challenged_team_id: "t1",
      description: "Nicht zugelassener Motor",
    }));
  });

  it("is read-only without scoring:admin", async () => {
    asUser(["scoring:read"]);
    wrap(<PartsChallengePanel eventId="e1" matches={matches} registrations={registrations} />);
    await screen.findAllByRole("listitem");
    expect(screen.queryByRole("button", { name: "Stattgeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Challenge erfassen/ })).not.toBeInTheDocument();
  });
});
