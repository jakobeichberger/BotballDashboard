/**
 * Forms that copy loaded data into a draft re-seed it during render (no
 * setState in an effect): another entity refills the form, a refetch of the
 * same one keeps the user's edits unless the form always followed the data.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useChanged } from "@/hooks/useChanged";
import CategoryRegistryEditor from "@/components/seasons/CategoryRegistryEditor";
import ChecklistConfirmDialog from "@/modules/scoring/extras/ChecklistConfirmDialog";
import MatchPenaltyDialog, { type PenaltyMatch } from "@/modules/scoring/extras/MatchPenaltyDialog";
import SeasonRulesEditor from "@/modules/scoring/extras/SeasonRulesEditor";
import OcrLayoutEditor from "@/modules/scoring/score-sheets/components/OcrLayoutEditor";
import type { ScoreSheetTemplate } from "@/modules/scoring/score-sheets/api/scoreSheets";
import SchemaEditor from "@/modules/scoring/sheet/SchemaEditor";
import type { ScoringSchema } from "@/api/types";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn() } }));

let data: Record<string, unknown> = {};
const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function withClient(queryClient: QueryClient) {
  return (ui: ReactNode) => <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  data = {};
  (api.get as any).mockImplementation((url: string) => Promise.resolve({ data: url in data ? structuredClone(data[url]) : [] }));
});

describe("useChanged", () => {
  it("is true only in the render in which a value changed", () => {
    const seen: boolean[] = [];
    const { rerender } = renderHook(({ values }) => { const changed = useChanged(values); seen.push(changed); return changed; }, { initialProps: { values: ["a", 1] as unknown[] } });
    rerender({ values: ["a", 1] });
    expect(seen).toEqual([false, false]);
    // React repeats the changed render right away with the stored values.
    rerender({ values: ["b", 1] });
    expect(seen).toEqual([false, false, true, false]);
  });
});

describe("ChecklistConfirmDialog", () => {
  const items = [{ key: "hands", label: "Hände weg", required: true, description: null }] as any;

  it("starts unticked on every opening", () => {
    const ui = (open: boolean) => <ChecklistConfirmDialog open={open} items={items} onCancel={vi.fn()} onConfirm={vi.fn()} />;
    const { rerender } = render(ui(true));
    fireEvent.click(screen.getByRole("checkbox", { name: /Hände weg/ }));
    expect(screen.getByRole("checkbox", { name: /Hände weg/ })).toBeChecked();
    rerender(ui(false));
    rerender(ui(true));
    expect(screen.getByRole("checkbox", { name: /Hände weg/ })).not.toBeChecked();
  });
});

describe("MatchPenaltyDialog", () => {
  const match = (id: string, yellow: boolean): PenaltyMatch => ({ id, version: 1, yellow_card: yellow, red_card: false, is_disqualified: false });
  const ui = (m: PenaltyMatch | null) => withClient(client())(<MatchPenaltyDialog match={m} title="Strafen" onClose={vi.fn()} onSaved={vi.fn()} />);

  it("shows the stored penalties of the opened match and refills for another one", () => {
    const { rerender } = render(ui(match("m1", true)));
    const yellow = () => screen.getByRole("checkbox", { name: /Gelbe Karte/ });
    expect(yellow()).toBeChecked();
    fireEvent.click(yellow());
    fireEvent.change(screen.getByRole("textbox", { name: /Begründung/ }), { target: { value: "Irrtum" } });
    expect(yellow()).not.toBeChecked();

    rerender(ui(match("m2", false)));
    expect(yellow()).not.toBeChecked();
    expect(screen.getByRole("textbox", { name: /Begründung/ })).toHaveValue("");
    rerender(ui(match("m3", true)));
    expect(yellow()).toBeChecked();
  });
});

describe("CategoryRegistryEditor", () => {
  const row = (label: string) => ({ key: "botball", label_de: label, label_en: label, kind: "botball", formula_preset: null, run_count: null, counted_runs: null, rank_per_bracket: false });

  it("fills the rows per season and keeps edits when the same season refetches", async () => {
    data = { "/seasons/s1/categories": [row("Eins")], "/seasons/s2/categories": [row("Zwei")], "/scoring/formulas/reference": {} };
    const queryClient = client();
    const wrap = withClient(queryClient);
    const { rerender } = render(wrap(<CategoryRegistryEditor seasonId="s1" />));
    const labelDe = () => screen.getByRole("textbox", { name: "Bezeichnung (DE)" });
    await waitFor(() => expect(labelDe()).toHaveValue("Eins"));

    fireEvent.change(labelDe(), { target: { value: "Bearbeitet" } });
    data["/seasons/s1/categories"] = [row("Vom Server")];
    await act(() => queryClient.invalidateQueries({ queryKey: ["season-categories", "s1"] }));
    // Let the observers render the refetched list before checking.
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(queryClient.getQueryData(["season-categories", "s1"])).toEqual([row("Vom Server")]);
    expect(labelDe()).toHaveValue("Bearbeitet");

    rerender(wrap(<CategoryRegistryEditor seasonId="s2" />));
    await waitFor(() => expect(labelDe()).toHaveValue("Zwei"));
  });
});

describe("SeasonRulesEditor", () => {
  const rules = (seasonId: string, label: string) => ({ season_id: seasonId, tiebreakers: [{ key: "a", label, direction: "max", source: "sheet", sheet_keys: [], replay_only: false }], finals_replay: false, end_contact_bonus_percent: 25, referee_checklist: [] });

  it("loads the rules of the chosen season into the draft", async () => {
    data = { "/scoring/seasons/s1/rules": rules("s1", "Erste"), "/scoring/seasons/s2/rules": rules("s2", "Zweite") };
    const wrap = withClient(client());
    const { rerender } = render(wrap(<SeasonRulesEditor seasonId="s1" onMessage={vi.fn()} />));
    const tiebreaker = () => screen.getByRole("textbox", { name: "Tie-Breaker" });
    await waitFor(() => expect(tiebreaker()).toHaveValue("Erste"));
    fireEvent.change(tiebreaker(), { target: { value: "Bearbeitet" } });
    expect(tiebreaker()).toHaveValue("Bearbeitet");
    rerender(wrap(<SeasonRulesEditor seasonId="s2" onMessage={vi.fn()} />));
    await waitFor(() => expect(tiebreaker()).toHaveValue("Zweite"));
  });
});

describe("SchemaEditor", () => {
  const schema = (id: string, label: string) => ({
    id, event_id: "e1", version: 1, is_active: true, fields: [],
    definition: { sides: [], sections: [{ key: "zone", label, fields: [{ key: "x", label: "X" }], multipliers: [] }] },
  }) as unknown as ScoringSchema;

  it("keeps edits for the same schema and loads a newly activated one", () => {
    const first = schema("v1", "Zone A");
    const wrap = withClient(client());
    const { rerender } = render(wrap(<SchemaEditor eventId="e1" schema={first} onMessage={vi.fn()} />));
    const section = () => screen.getByRole("textbox", { name: "Bereichsname" });
    expect(section()).toHaveValue("Zone A");
    fireEvent.change(section(), { target: { value: "Bearbeitet" } });
    rerender(wrap(<SchemaEditor eventId="e1" schema={first} onMessage={vi.fn()} />));
    expect(section()).toHaveValue("Bearbeitet");
    rerender(wrap(<SchemaEditor eventId="e1" schema={schema("v2", "Zone B")} onMessage={vi.fn()} />));
    expect(section()).toHaveValue("Zone B");
  });
});

describe("OcrLayoutEditor", () => {
  const template = (id: string, x: number): ScoreSheetTemplate => ({
    id, season_id: "s1", competition_level_id: null, label: "2026", year: 2026, game_theme: null, is_active: true,
    file_name: "sheet.pdf", file_size_bytes: 1, ocr_status: "done", confirmed_fields_count: 1, uploaded_at: "", uploaded_by: "u",
    confirmed_by: "u", confirmed_at: "", extracted_fields: null,
    confirmed_fields: [{ key: "cubes", label: "Würfel", multiplier: 1, max_value: null, type: "count", section: null, notes: null }],
    page_width: 1000, page_height: 1000, anchors: null,
    field_regions: [{ key: "cubes", x, y: 0, width: 100, height: 100 }],
    validation_rules: null,
  } as ScoreSheetTemplate);

  it("keeps edits while the template is unchanged and loads another template's layout", () => {
    const first = template("tpl1", 100);
    const wrap = withClient(client());
    const { rerender } = render(wrap(<OcrLayoutEditor template={first} onSaved={vi.fn()} />));
    const left = () => screen.getByRole("spinbutton", { name: "Links % für cubes" });
    expect(left()).toHaveValue(10);
    fireEvent.change(left(), { target: { value: "30" } });
    rerender(wrap(<OcrLayoutEditor template={first} onSaved={vi.fn()} />));
    expect(left()).toHaveValue(30);
    rerender(wrap(<OcrLayoutEditor template={template("tpl2", 500)} onSaved={vi.fn()} />));
    expect(left()).toHaveValue(50);
  });
});
