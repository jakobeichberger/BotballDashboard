import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import fixtures from "@/modules/scoring/sheet/__fixtures__/score-sheet-cases.json";
import SchemaEditor from "@/modules/scoring/sheet/SchemaEditor";
import SheetForm from "@/modules/scoring/sheet/SheetForm";
import { definitionProblems } from "@/modules/scoring/sheet/definitionProblems";
import SeasonRulesEditor from "@/modules/scoring/extras/SeasonRulesEditor";
import ScoutingPage from "@/pages/ScoutingPage";
import { fromFlatFields, type SheetDefinition } from "@/modules/scoring/sheet/calculator";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

const DEF_2025 = fixtures.schemas.botball_2025.definition as unknown as SheetDefinition;

function mockGet(data: Record<string, unknown>) {
  (api.get as any).mockImplementation((url: string) => Promise.resolve({ data: url in data ? data[url] : [] }));
}

function wrap(ui: ReactNode, path = "/events/e1/x") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path="/events/:eventId/*" element={ui} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function login(permissions: string[], superuser = false) {
  useAuthStore.setState({
    accessToken: "token",
    user: { id: "u1", email: "u@example.org", display_name: "User", is_superuser: superuser, preferred_language: "de", theme: "system", roles: ["mentor"], permissions } as any,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  login([], true);
});

describe("SheetForm", () => {
  it("previews the section breakdown with area multipliers and either-or", async () => {
    const values = { "A.serving_red_pom": 3, "A.serving_orange_pom": 3, "A.serving_yellow_pom": 3, "A.serving_full_pom_sets": 3, "A.serving_full_trays": 1 };
    wrap(<SheetForm definition={DEF_2025} values={values} onChange={() => {}} />);
    const serving = screen.getByRole("group", { name: "Serving Station" });
    expect(within(serving).getByText("135")).toBeInTheDocument();
    expect(serving).toHaveTextContent("45 × 3 = 135");
    expect(screen.getByRole("tab", { name: "Seite A · 135" })).toBeInTheDocument();
    expect(screen.getByText(/Total A \+ B =/)).toHaveTextContent("135");
  });

  it("reports values above the sheet maximum", () => {
    wrap(<SheetForm definition={DEF_2025} values={{ "A.fry_potato": 3 }} onChange={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("A.fry_potato must be at most 2");
  });

  it("never shows the internal key of an unnamed section", () => {
    const flat = fromFlatFields([{ key: "points", label: "Punkte", type: "count" } as any]);
    wrap(<SheetForm definition={flat} values={{}} onChange={() => {}} />);
    expect(screen.queryByText("section_1")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Eingaben" })).toBeInTheDocument();
  });
});

describe("SchemaEditor", () => {
  const template = { id: "botball_2025", name: "Botball 2025 – Restaurant", year: 2025, complete: true, source: "sheet", notes: "", definition: DEF_2025 };

  it("loads a template and saves it as a structured definition", async () => {
    mockGet({ "/scoring/schema-templates": [template], "/seasons/competition-levels/all": [], "/scoring/schemas": [] });
    (api.post as any).mockResolvedValue({ data: {} });
    const onMessage = vi.fn();
    wrap(<SchemaEditor eventId="e1" onMessage={onMessage} />);
    const select = await screen.findByRole("combobox", { name: "Vorlage" });
    await waitFor(() => expect(within(select).getByRole("option", { name: /Botball 2025/ })).toBeInTheDocument());
    await userEvent.selectOptions(select, "botball_2025");
    await userEvent.click(screen.getByRole("button", { name: "Laden" }));
    expect(screen.getAllByRole("textbox", { name: "Bereichsname" })).toHaveLength(DEF_2025.sections.length);
    expect(screen.getByRole("checkbox", { name: /Getrennte Seiten A\/B/ })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Neue Version aktivieren" }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, body] = (api.post as any).mock.calls[0];
    expect(url).toBe("/v1/events/e1/scoring-schema/versions");
    expect(body.definition).toEqual(DEF_2025);
    expect(body.activate).toBe(true);
  });

  it("offers a JSON fallback that accepts a flat field list", async () => {
    mockGet({});
    (api.post as any).mockResolvedValue({ data: {} });
    wrap(<SchemaEditor eventId="e1" onMessage={() => {}} />);
    await userEvent.click(screen.getByRole("tab", { name: "JSON" }));
    const textarea = screen.getByRole("textbox", { name: "Schema-JSON" });
    fireEvent.change(textarea, { target: { value: JSON.stringify([{ key: "pieces", label: "Pieces", multiplier: 3 }]) } });
    await userEvent.click(screen.getByRole("button", { name: "Neue Version aktivieren" }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect((api.post as any).mock.calls[0][1]).toMatchObject({ fields: [{ key: "pieces", multiplier: 3 }] });
  });

  it("clones another event's schema", async () => {
    mockGet({ "/scoring/schemas": [{ id: "s-ecer", season_id: "s", season_name: "2026", event_id: "ecer", event_name: "ECER 2026", competition_level_id: null, competition_level_name: null, version: 2, structured: true, field_count: 10 }] });
    (api.post as any).mockResolvedValue({ data: {} });
    wrap(<SchemaEditor eventId="e1" onMessage={() => {}} />);
    const select = screen.getByRole("combobox", { name: "Schema zum Klonen" });
    await waitFor(() => expect(within(select).getByRole("option", { name: /ECER 2026/ })).toBeInTheDocument());
    await userEvent.selectOptions(select, "s-ecer");
    await userEvent.click(screen.getByRole("button", { name: "Klonen" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/scoring/events/e1/scoring-schema/clone", { source_schema_id: "s-ecer", competition_level_id: null, activate: true }));
  });

  it("flags duplicate keys before saving", () => {
    const broken: SheetDefinition = { sides: [], sections: [{ key: "zone", label: "Zone", fields: [{ key: "x", label: "X" }], multipliers: [{ key: "x", label: "Dup", type: "boolean", factor: 2 }] }] };
    expect(definitionProblems(broken)).toContain("Schlüssel „x“ ist doppelt.");
    expect(definitionProblems(DEF_2025)).toEqual([]);
  });
});

describe("SeasonRulesEditor", () => {
  it("applies a game-review preset and saves the rules", async () => {
    const preset = { id: "botball_2026", name: "Botball 2026", finals_replay: true, tiebreakers: [{ key: "a", label: "Sorted cubes", direction: "max", source: "sheet", sheet_keys: ["external_dock_sorted_cubes"], replay_only: false }] };
    mockGet({ "/scoring/seasons/s1/rules": { season_id: "s1", tiebreakers: [], finals_replay: false, end_contact_bonus_percent: 25, referee_checklist: [] }, "/scoring/tiebreaker-presets": [preset] });
    (api.put as any).mockResolvedValue({ data: {} });
    wrap(<SeasonRulesEditor seasonId="s1" onMessage={() => {}} />);
    const select = await screen.findByRole("combobox", { name: "Vorlage" });
    await waitFor(() => expect(within(select).getByRole("option", { name: "Botball 2026" })).toBeInTheDocument());
    await userEvent.selectOptions(select, "botball_2026");
    await userEvent.click(screen.getByRole("button", { name: "Übernehmen" }));
    expect(screen.getByRole("textbox", { name: "Tie-Breaker" })).toHaveValue("Sorted cubes");
    await userEvent.click(screen.getByRole("button", { name: "Prüfpunkt" }));
    await userEvent.click(screen.getByRole("button", { name: "Regeln speichern" }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const body = (api.put as any).mock.calls[0][1];
    expect(body.finals_replay).toBe(true);
    expect(body.tiebreakers[0].sheet_keys).toEqual(["external_dock_sorted_cubes"]);
    expect(body.referee_checklist).toHaveLength(1);
  });
});

describe("ScoutingPage", () => {
  it("shows own and external teams in one ranking and records a note for the mentor's team", async () => {
    login(["scoring:read", "scoring:write"]);
    mockGet({
      "/v1/events/e1": { id: "e1", season_id: "s1", slug: "ecer" },
      "/scoring/seasons/s1/external-teams": [{ id: "x1", season_id: "s1", name: "Robo Masters", number: "25-0538", country: "KW", school: null, source: "observed", notes: null, created_at: "" }],
      "/scoring/events/e1/opponent-ranking": [
        { rank: 1, kind: "external", team_id: "x1", team_name: "Robo Masters", team_number: "25-0538", country: "KW", seed_score: 390, best_score: 400, runs: 3, official_rank: null },
        { rank: 2, kind: "internal", team_id: "t1", team_name: "Our Team", team_number: null, country: "AT", seed_score: 250, best_score: 300, runs: 3, official_rank: 1 },
      ],
      "/teams/mine": [{ id: "t1", name: "Our Team" }],
      "/scoring/events/e1/scouting/notes": [],
      "/scoring/events/e1/scouting/observations": [],
    });
    (api.post as any).mockResolvedValue({ data: {} });
    wrap(<ScoutingPage />, "/events/e1/scouting");
    const table = await screen.findByRole("table");
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(3));
    expect(within(table).getByText("eigenes Team")).toBeInTheDocument();
    await userEvent.click(within(table).getByRole("button", { name: "Robo Masters" }));
    await userEvent.type(await screen.findByRole("textbox", { name: "Notiz" }), "Fast drive base");
    await userEvent.click(screen.getByRole("button", { name: "Notiz speichern" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/scoring/events/e1/scouting/notes", { external_team_id: "x1", owner_team_id: "t1", body: "Fast drive base", threat_level: null }));
  });
});
