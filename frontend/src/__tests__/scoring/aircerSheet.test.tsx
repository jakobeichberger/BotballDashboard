import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import fixtures from "@/modules/scoring/sheet/__fixtures__/score-sheet-cases.json";
import SchemaEditor from "@/modules/scoring/sheet/SchemaEditor";
import SheetForm from "@/modules/scoring/sheet/SheetForm";
import { definitionProblems } from "@/modules/scoring/sheet/definitionProblems";
import { computeSheet, inputFields, validate, type SheetDefinition, type SheetMultiplier } from "@/modules/scoring/sheet/calculator";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

// AIRCER 2026 – the template as shipped by the backend (same fixture as the parity tests).
const AIRCER = fixtures.schemas.aircer_2026.definition as unknown as SheetDefinition;

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => vi.clearAllMocks());

describe("AIRCER sheet in the calculator", () => {
  it("is one side with plain keys and sum inputs instead of the sum key", () => {
    const keys = inputFields(AIRCER).map((spec) => spec.key);
    expect(AIRCER.sides).toEqual([]);
    expect(keys).toEqual(expect.arrayContaining(["centrifuge_sorted_drums", "centrifuge_unsorted_drums", "waste_rocks", "safety_lever", "upper_deck_max_stack_height", "upper_deck_stack_count"]));
    expect(keys).not.toContain("upper_deck_stacks");
    expect(validate({ upper_deck_stacks: 2 }, AIRCER)).toEqual(["upper_deck_stacks is not part of the active scoring schema"]);
    const result = computeSheet({ waste_rocks: 1 }, AIRCER);
    expect(result.sides.map((side) => side.side)).toEqual([null]);
    expect(result.total).toBe(20);
  });

  it("previews a clamped total when a sum input is above its maximum", () => {
    const result = computeSheet({ upper_deck_unsorted_cubes: 1, upper_deck_max_stack_height: 40 }, AIRCER);
    expect(result.errors).toEqual(["upper_deck_max_stack_height must be at most 28"]);
    expect(result.total).toBe(280);
  });
});

describe("AIRCER SheetForm", () => {
  it("renders one side, the sum inputs and the penalty checkbox", async () => {
    const onChange = vi.fn();
    const values = { upper_deck_sorted_cubes: 4, upper_deck_unsorted_cubes: 2, upper_deck_other_pieces: 1, upper_deck_max_stack_height: 3, upper_deck_stack_count: 2, incineration_drums: 1, incineration_variety: 1, incineration_restricted_area: true };
    wrap(<SheetForm definition={AIRCER} values={values} onChange={onChange} />);
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    const upper = screen.getByRole("group", { name: "Upper Storage Deck" });
    expect(upper).toHaveTextContent("Max Stack Height + # of Stacks: Bereich × (Max Stack Height + # of Stacks)");
    expect(upper).toHaveTextContent("101 × 5 = 505");
    const plant = screen.getByRole("group", { name: "Incineration Plant" });
    const penalty = within(plant).getByRole("checkbox", { name: /Restricted Area/ });
    expect(penalty).toBeChecked();
    expect(penalty.closest("label")).toHaveTextContent("Bereich × 0.5 (Abzug)");
    expect(plant).toHaveTextContent("15 × 0.5 = 7.5");
    await userEvent.click(within(upper).getByRole("button", { name: "# of Stacks um 1 erhöhen" }));
    expect(onChange).toHaveBeenCalledWith("upper_deck_stack_count", 3);
  });

  it("shows the product and zero switches in the hints", () => {
    const product = fixtures.schemas.aircer_2026_product.definition as unknown as SheetDefinition;
    const zero = fixtures.schemas.aircer_2026_zero.definition as unknown as SheetDefinition;
    const { unmount } = wrap(<SheetForm definition={product} values={{}} onChange={() => {}} />);
    expect(screen.getByRole("group", { name: "Research Table" })).toHaveTextContent("Bereich × (Max Stack Height × # of Stacks)");
    unmount();
    wrap(<SheetForm definition={zero} values={{}} onChange={() => {}} />);
    expect(screen.getByRole("group", { name: "Lower Storage Deck" })).toHaveTextContent("0 → Bereich 0");
  });
});

describe("AIRCER SchemaEditor", () => {
  const template = { id: "aircer_2026", name: "AIRCER 2026 – Laboratory Lockdown", year: 2026, complete: true, source: "sheet", notes: "", definition: AIRCER };

  async function loadTemplate() {
    (api.get as any).mockImplementation((url: string) => Promise.resolve({ data: url === "/scoring/schema-templates" ? [template] : [] }));
    (api.post as any).mockResolvedValue({ data: {} });
    wrap(<SchemaEditor eventId="e1" onMessage={() => {}} />);
    const select = await screen.findByRole("combobox", { name: "Vorlage" });
    await waitFor(() => expect(within(select).getByRole("option", { name: /AIRCER 2026/ })).toBeInTheDocument());
    await userEvent.selectOptions(select, "aircer_2026");
    await userEvent.click(screen.getByRole("button", { name: "Laden" }));
  }

  const multiplier = (definition: SheetDefinition, section: string) => definition.sections.find((s) => s.key === section)!.multipliers[0] as SheetMultiplier;

  it("keeps every construct of the template and saves it unchanged", async () => {
    await loadTemplate();
    expect(screen.getAllByRole("textbox", { name: "Bereichsname" })).toHaveLength(AIRCER.sections.length);
    expect(screen.getByRole("checkbox", { name: /Getrennte Seiten A\/B/ })).not.toBeChecked();
    expect(screen.getAllByRole("combobox", { name: "Verknüpfung der Werte" })).toHaveLength(2);
    expect(screen.getAllByRole("checkbox", { name: /Faktor unter 1 anwenden/ }).filter((box) => (box as HTMLInputElement).checked)).toHaveLength(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Neue Version aktivieren" }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect((api.post as any).mock.calls[0][1].definition).toEqual(AIRCER);
  });

  it("switches sum to product and the zero rule in the structured editor", async () => {
    await loadTemplate();
    const [upperMode] = screen.getAllByRole("combobox", { name: "Verknüpfung der Werte" });
    await userEvent.selectOptions(upperMode, "product");
    const [trays] = screen.getAllByRole("combobox", { name: "Leeres Kästchen (0)" });
    await userEvent.selectOptions(trays, "zero");
    await userEvent.click(screen.getByRole("button", { name: "Neue Version aktivieren" }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const saved = (api.post as any).mock.calls[0][1].definition as SheetDefinition;
    expect(multiplier(saved, "upper_storage_deck").mode).toBe("product");
    expect(multiplier(saved, "research_table").mode).toBe("sum");
    expect(multiplier(saved, "lower_storage_deck").zero_means).toBe("zero");
  });

  it("turns a multiplier into a sum with two inputs", async () => {
    await loadTemplate();
    const [trayType] = screen.getAllByRole("combobox", { name: "Multiplikator-Art" });
    await userEvent.selectOptions(trayType, "sum");
    expect(screen.getAllByRole("combobox", { name: "Verknüpfung der Werte" })).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "Neue Version aktivieren" }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const trays = multiplier((api.post as any).mock.calls[0][1].definition, "lower_storage_deck");
    expect(trays).toMatchObject({ type: "sum", mode: "sum", inputs: [{ key: "lower_deck_filled_trays_a" }, { key: "lower_deck_filled_trays_b" }] });
  });
});

describe("definitionProblems for the new multiplier kinds", () => {
  const zone = (multipliers: SheetDefinition["sections"][number]["multipliers"]): SheetDefinition => ({ sides: [], sections: [{ key: "zone", label: "Zone", fields: [{ key: "x", label: "X" }], multipliers }] });

  it("accepts the AIRCER template", () => {
    expect(definitionProblems(AIRCER)).toEqual([]);
  });

  it("flags a sum without inputs, a sum as either-or alternative and duplicate input keys", () => {
    expect(definitionProblems(zone([{ key: "s", label: "S", type: "sum", inputs: [] }]))).toEqual(["S: eine Summe braucht mindestens einen Wert."]);
    expect(definitionProblems(zone([{ key: "e", label: "E", either: [{ key: "s", label: "S", type: "sum", inputs: [{ key: "a", label: "A" }] }, { key: "b", label: "B" }] }]))).toContain("S: eine Summe kann keine Entweder-oder-Alternative sein.");
    expect(definitionProblems(zone([{ key: "s", label: "S", type: "sum", inputs: [{ key: "x", label: "Dup" }] }]))).toContain("Schlüssel „x“ ist doppelt.");
  });
});
