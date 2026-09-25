import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import PhaseManager from "@/components/events/PhaseManager";
import RegistrationManager from "@/components/events/RegistrationManager";
import EventBracketWeights from "@/components/events/EventBracketWeights";
import AllianceStandings from "@/components/events/AllianceStandings";
import { api } from "@/lib/api";
import { formatScore } from "@/i18n/format";
import type { EventPhase } from "@/api/types";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const get = api.get as ReturnType<typeof vi.fn>;
const ok = { data: {} };

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

function phase(overrides: Partial<EventPhase>): EventPhase {
  return { id: "ph", event_id: "e1", name: "Seeding", phase_type: "seeding", sort_order: 0, status: "draft", rounds: 3, starts_at: null, ends_at: null, settings: {}, ...overrides };
}

beforeEach(() => {
  vi.clearAllMocks();
  for (const method of ["post", "patch", "put", "delete"] as const) (api[method] as ReturnType<typeof vi.fn>).mockResolvedValue(ok);
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

const editForm = () => screen.getByRole("button", { name: "Speichern" }).closest("form")!;

describe("PhaseManager", () => {
  const phases = [
    phase({ id: "p1", name: "Seeding", status: "live" }),
    phase({ id: "p2", name: "Finale", phase_type: "final", sort_order: 3, status: "draft", rounds: 1 }),
  ];
  beforeEach(() => get.mockResolvedValue({ data: phases }));

  it("does not offer deleting live or completed phases", async () => {
    wrap(<PhaseManager eventId="e1" />);
    expect(await screen.findByRole("button", { name: "Phase Seeding löschen" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Phase Finale löschen" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/v1/events/e1/phases/p2"));
  });

  it("edits a phase; the type of a live phase stays locked", async () => {
    wrap(<PhaseManager eventId="e1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Phase Seeding bearbeiten" }));
    const form = within(editForm());
    expect(form.getByRole("combobox", { name: "Phasentyp" })).toBeDisabled();
    expect(form.getByText(/Typ ist gesperrt/)).toBeInTheDocument();
    fireEvent.change(form.getByRole("textbox", { name: "Phasenname" }), { target: { value: "Seeding Tag 1" } });
    fireEvent.change(form.getByRole("combobox", { name: "Status" }), { target: { value: "completed" } });
    fireEvent.click(form.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/v1/events/e1/phases/p1", { name: "Seeding Tag 1", status: "completed", rounds: 3 }));
  });

  it("changes the type of a draft phase", async () => {
    wrap(<PhaseManager eventId="e1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Phase Finale bearbeiten" }));
    fireEvent.change(within(editForm()).getByRole("combobox", { name: "Phasentyp" }), { target: { value: "double_elimination" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/v1/events/e1/phases/p2", expect.objectContaining({ phase_type: "double_elimination" })));
  });

  it("appends new phases after the highest sort order", async () => {
    wrap(<PhaseManager eventId="e1" />);
    await screen.findByText(/Finale/);
    const form = screen.getByRole("button", { name: "Phase hinzufügen" }).closest("form")!;
    fireEvent.change(within(form).getByRole("textbox", { name: "Phasenname" }), { target: { value: "Alliance" } });
    fireEvent.click(within(form).getByRole("button", { name: "Phase hinzufügen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/v1/events/e1/phases", { name: "Alliance", phase_type: "seeding", rounds: 3, sort_order: 4 }));
  });

  it("shows why the backend refused a change", async () => {
    (api.patch as ReturnType<typeof vi.fn>).mockRejectedValue({ response: { data: { detail: "Another phase already uses this sort order" } } });
    wrap(<PhaseManager eventId="e1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Phase Finale bearbeiten" }));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another phase already uses this sort order");
  });
});

describe("RegistrationManager", () => {
  beforeEach(() => {
    get.mockImplementation((url: string) => {
      if (url === "/teams") return Promise.resolve({ data: [{ id: "t1", name: "Alpha" }, { id: "t2", name: "Beta" }, { id: "t3", name: "Gamma" }] });
      return Promise.resolve({ data: [
        { id: "r1", event_id: "e1", team_id: "t1", team_name: "Alpha", team_number: "A-1", competition_level_id: null, category: "botball", seed_number: null, checked_in_at: "2026-05-01T08:15:00Z", notes: null },
        { id: "r2", event_id: "e1", team_id: "t2", team_name: "Beta", team_number: null, competition_level_id: null, category: "botball", seed_number: null, checked_in_at: null, notes: null },
      ] });
    });
  });

  it("shows the check-in state and checks a team in or out", async () => {
    wrap(<RegistrationManager eventId="e1" />);
    expect(await screen.findByText("1 von 2 eingecheckt")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Alpha eingecheckt" })).toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: "Beta eingecheckt" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/v1/events/e1/registrations/r2", { checked_in: true }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Alpha eingecheckt" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/v1/events/e1/registrations/r1", { checked_in: false }));
  });

  it("registers only unregistered teams and removes a registration", async () => {
    wrap(<RegistrationManager eventId="e1" />);
    const select = await screen.findByRole("combobox", { name: "Team registrieren" });
    await within(select).findByRole("option", { name: "Gamma" });
    expect(within(select).queryByRole("option", { name: "Alpha" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Registrierung von Beta entfernen" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/v1/events/e1/registrations/r2"));
  });
});

describe("EventBracketWeights", () => {
  beforeEach(() => get.mockResolvedValue({ data: { A: 1, B: 0.8 } }));

  it("saves the weights of the chosen category", async () => {
    wrap(<EventBracketWeights eventId="e1" />);
    expect(await screen.findByDisplayValue("0.8")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Kategorie" }), { target: { value: "open" } });
    await waitFor(() => expect(get).toHaveBeenCalledWith("/v1/events/e1/bracket-weights", { params: { category: "open" } }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Gewichtung 2" }), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Gewichtung speichern" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/v1/events/e1/bracket-weights", { weights: { A: 1, B: 0.5 } }, { params: { category: "open" } }));
    expect(await screen.findByRole("status")).toHaveTextContent("Bracket-Gewichtung gespeichert.");
  });

  it("returns to the season weights", async () => {
    wrap(<EventBracketWeights eventId="e1" />);
    await screen.findByDisplayValue("0.8");
    fireEvent.click(screen.getByRole("button", { name: /Saison-Gewichtung verwenden/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/v1/events/e1/bracket-weights", { weights: {} }, { params: { category: "botball" } }));
  });
});

describe("AllianceStandings", () => {
  it("lists alliances with their runs, best and total score", async () => {
    get.mockResolvedValue({ data: [
      { rank: 1, team_ids: ["t1", "t2"], team_names: ["Alpha", "Beta"], runs: [{ match_id: "m1", round_number: 1, score: 120 }, { match_id: "m2", round_number: 2, score: 90 }], best_score: 120, total_score: 210 },
    ] });
    wrap(<AllianceStandings eventId="e1" phase={phase({ id: "pa", name: "Alliance", phase_type: "alliance" })} />);
    const row = (await screen.findByText("Alpha + Beta")).closest("tr")!;
    expect(get).toHaveBeenCalledWith("/v1/events/e1/phases/pa/alliances");
    expect(row).toHaveTextContent(`${formatScore(120)} · ${formatScore(90)}`);
    expect(row).toHaveTextContent(formatScore(210));
  });
});
