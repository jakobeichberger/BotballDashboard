import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import OcrLayoutEditor from "@/modules/scoring/score-sheets/components/OcrLayoutEditor";
import { compactRules, fitRegion, nextAnchorName, normalizeRegions, parseRules, rectFromPoints, rulesProblem } from "@/modules/scoring/score-sheets/layout";
import type { ScoreSheetTemplate } from "@/modules/scoring/score-sheets/api/scoreSheets";
import ScanReviewPage from "@/pages/ScanReviewPage";
import ScoreSheetsPage from "@/modules/scoring/score-sheets/pages/ScoreSheetsPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));

// jsdom has no PointerEvent; without it fireEvent.pointer* drops clientX/clientY.
if (!("PointerEvent" in window)) Object.defineProperty(window, "PointerEvent", { value: MouseEvent, configurable: true });

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

describe("OCR layout geometry", () => {
  it("normalizes pixel regions by the page size and keeps normalized ones", () => {
    expect(normalizeRegions([{ key: "a", x: 248, y: 351, width: 496, height: 175 }], 2480, 3508)).toEqual([
      { key: "a", x: 0.1, y: 0.1001, width: 0.2, height: 0.0499 },
    ]);
    expect(normalizeRegions([{ key: "b", x: 0.5, y: 0.5, width: 0.1, height: 0.1 }], 2480, 3508)[0].x).toBe(0.5);
    expect(normalizeRegions(null, 1, 1)).toEqual([]);
  });

  it("spans a box between two points in any drag direction and clips it to the page", () => {
    expect(rectFromPoints("a", { x: 0.6, y: 0.4 }, { x: 0.2, y: 0.1 })).toEqual({ key: "a", x: 0.2, y: 0.1, width: 0.4, height: 0.3 });
    expect(rectFromPoints("a", { x: 0.9, y: 0.9 }, { x: 1.4, y: -0.2 })).toEqual({ key: "a", x: 0.9, y: 0, width: 0.1, height: 0.9 });
  });

  it("keeps edited boxes inside the page", () => {
    expect(fitRegion({ key: "a", x: 0.95, y: 0.5, width: 0.2, height: 0.1 })).toEqual({ key: "a", x: 0.95, y: 0.5, width: 0.05, height: 0.1 });
  });
});

function template(overrides: Partial<ScoreSheetTemplate> = {}): ScoreSheetTemplate {
  return {
    id: "tpl", season_id: "s1", competition_level_id: null, label: "2026", year: 2026, game_theme: null, is_active: true,
    file_name: "sheet.pdf", file_size_bytes: 1, ocr_status: "done", confirmed_fields_count: 2, uploaded_at: "", uploaded_by: "u",
    confirmed_by: "u", confirmed_at: "", extracted_fields: null,
    confirmed_fields: [
      { key: "cubes", label: "Würfel", multiplier: 1, max_value: null, type: "count", section: null, notes: null },
      { key: "parked", label: "Geparkt", multiplier: 1, max_value: null, type: "boolean", section: null, notes: null },
    ],
    page_width: 1000, page_height: 2000,
    anchors: [{ name: "corner", x: 0, y: 0, width: 10, height: 10 }],
    field_regions: [{ key: "cubes", x: 100, y: 200, width: 300, height: 100 }],
    validation_rules: { strict: true },
    ...overrides,
  };
}

describe("OcrLayoutEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.patch as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
  });

  it("asks for confirmed fields first", () => {
    wrap(<OcrLayoutEditor template={template({ confirmed_fields: [] })} onSaved={vi.fn()} />);
    expect(screen.getByText(/Erst die Felder bestätigen/)).toBeInTheDocument();
  });

  it("shows stored pixel regions as percentages and saves normalized boxes", async () => {
    const onSaved = vi.fn();
    wrap(<OcrLayoutEditor template={template()} onSaved={onSaved} />);
    expect(screen.getByRole("spinbutton", { name: "Links % für cubes" })).toHaveValue(10);
    expect(screen.getByRole("spinbutton", { name: "Oben % für cubes" })).toHaveValue(10);
    expect(screen.getByText("1 von 2 Feldern haben ein Rechteck.")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("spinbutton", { name: "Breite % für cubes" }), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "Rechteck anlegen" }));
    fireEvent.click(screen.getByRole("button", { name: "Layout speichern" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch).toHaveBeenCalledWith("/scoring/score-sheets/tpl/layout", {
      page_width: 1000,
      page_height: 2000,
      // Pixel anchors are normalized like regions; rules in an old shape fall back to the defaults.
      anchors: [{ name: "corner", x: 0, y: 0, width: 0.01, height: 0.005 }],
      field_regions: [
        { key: "cubes", x: 0.1, y: 0.1, width: 0.25, height: 0.05 },
        { key: "parked", x: 0.1, y: 0.1, width: 0.1, height: 0.03 },
      ],
      validation_rules: { min_confidence: 0.85, fields: [], sums: [] },
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("draws anchors in anchor mode and saves them with the edited rules", async () => {
    wrap(<OcrLayoutEditor template={template({ anchors: null, validation_rules: null })} onSaved={vi.fn()} />);
    const surface = screen.getByTestId("ocr-layout-surface");
    surface.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 400, right: 200, bottom: 400, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.change(screen.getByRole("combobox", { name: "Zeichnen" }), { target: { value: "anchors" } });
    expect(screen.queryByRole("combobox", { name: "Rechteck zeichnen für" })).not.toBeInTheDocument();
    fireEvent.pointerDown(surface, { clientX: 4, clientY: 8, pointerId: 1 });
    fireEvent.pointerUp(surface, { clientX: 12, clientY: 16, pointerId: 1 });
    expect(screen.getByRole("textbox", { name: "Name von Anker 1" })).toHaveValue("anchor_1");
    expect(screen.getByText(/Mindestens 2 Anker nötig/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Anker hinzufügen" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Name von Anker 2" }), { target: { value: "unten rechts" } });
    expect(screen.queryByText(/Mindestens 2 Anker nötig/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("spinbutton", { name: "Mindest-Konfidenz (%)" }), { target: { value: "70" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Maximum für cubes" }), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "cubes muss eine Ganzzahl sein" }));
    // Boolean fields have no numeric limits.
    expect(screen.queryByRole("spinbutton", { name: "Maximum für parked" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Layout speichern" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    const body = (api.patch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(body.anchors).toEqual([
      { name: "anchor_1", x: 0.02, y: 0.02, width: 0.04, height: 0.02 },
      { name: "unten rechts", x: 0.02, y: 0.02, width: 0.03, height: 0.02 },
    ]);
    expect(body.validation_rules).toEqual({
      min_confidence: 0.7,
      fields: [{ key: "cubes", min_value: null, max_value: 12, integer: true, min_confidence: null }],
      sums: [],
    });
  });

  it("blocks saving an incomplete sum rule and explains why", async () => {
    wrap(<OcrLayoutEditor template={template()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Summenregel hinzufügen" }));
    const save = screen.getByRole("button", { name: "Layout speichern" });
    expect(screen.getByRole("alert")).toHaveTextContent("Summenregel 1 braucht eine Bezeichnung.");
    expect(save).toBeDisabled();

    const rule = screen.getByRole("group", { name: "Summenregel 1" });
    fireEvent.change(within(rule).getByRole("textbox", { name: "Bezeichnung" }), { target: { value: "Objekte" } });
    fireEvent.click(within(rule).getByRole("checkbox", { name: "Würfel" }));
    expect(screen.getByRole("alert")).toHaveTextContent("mindestens zwei Felder");
    fireEvent.click(within(rule).getByRole("checkbox", { name: "Geparkt" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Minimum oder Maximum");
    fireEvent.change(within(rule).getByRole("spinbutton", { name: "Maximum" }), { target: { value: "13" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(save);
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect((api.patch as ReturnType<typeof vi.fn>).mock.calls[0][1].validation_rules.sums).toEqual([
      { label: "Objekte", keys: ["cubes", "parked"], min_value: null, max_value: 13 },
    ]);
  });

  it("loads stored rules and drops those of removed fields", () => {
    wrap(
      <OcrLayoutEditor
        template={template({
          validation_rules: {
            min_confidence: 0.6,
            fields: [{ key: "cubes", min_value: 1, max_value: null, integer: false, min_confidence: 0.9 }, { key: "gone", max_value: 3 }],
            sums: [],
          },
        })}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByRole("spinbutton", { name: "Mindest-Konfidenz (%)" })).toHaveValue(60);
    expect(screen.getByRole("spinbutton", { name: "Minimum für cubes" })).toHaveValue(1);
    expect(screen.getByRole("spinbutton", { name: "Mindest-Konfidenz % für cubes" })).toHaveValue(90);
  });
});

describe("OCR rule helpers", () => {
  it("parses stored rules defensively and compacts empty field rules", () => {
    const keys = new Set(["a", "b"]);
    expect(parseRules({ strict: true }, keys)).toEqual({ min_confidence: 0.85, fields: [], sums: [] });
    const parsed = parseRules({ min_confidence: 2, fields: [{ key: "a" }, { key: "x", max_value: 1 }], sums: [{ label: "S", keys: ["a", "x", "b"], max_value: 4 }] }, keys);
    expect(parsed.min_confidence).toBe(0.85);
    expect(parsed.fields).toEqual([{ key: "a", min_value: null, max_value: null, integer: false, min_confidence: null }]);
    expect(parsed.sums[0].keys).toEqual(["a", "b"]);
    expect(compactRules(parsed).fields).toEqual([]);
  });

  it("names new anchors without clashing and reports the first rule problem", () => {
    expect(nextAnchorName([{ name: "anchor_2", x: 0, y: 0, width: 0.1, height: 0.1 }])).toBe("anchor_3");
    expect(rulesProblem({ min_confidence: 0.8, fields: [{ key: "a", min_value: 5, max_value: 1, integer: false, min_confidence: null }], sums: [] })).toEqual({ problem: "fieldRange", name: "a" });
    expect(rulesProblem({ min_confidence: 0.8, fields: [], sums: [{ label: "S", keys: ["a", "b"], min_value: 9, max_value: 3 }] })).toEqual({ problem: "sumRange", name: "S" });
  });
});

describe("OCR review reasons", () => {
  it("shows why a value was flagged in the user's language", async () => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: { id: "u", is_superuser: false, roles: [], permissions: ["scoring:read", "scoring:write"] } as never });
    (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.endsWith("/score-sheet-scans")) {
        return Promise.resolve({ data: [
          { id: "s1", template_id: "t", team_id: "t1", file_name: "scan.jpg", status: "review", error: null, created_at: "",
            extracted_values: [{ key: "cubes", value: 13, confidence: 0.9, cropUrl: "/api/crop.png", requiresReview: true, reasons: ["above_maximum", "anchors_not_found"] }] },
        ] });
      }
      if (url === "/v1/events/ev") return Promise.resolve({ data: { id: "ev", season_id: "se" } });
      if (url === "/crop.png") return Promise.resolve({ data: new Blob() });
      return Promise.resolve({ data: [] });
    });
    wrap(
      <MemoryRouter initialEntries={["/events/ev/scans"]}>
        <Routes><Route path="/events/:eventId/scans" element={<ScanReviewPage />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/über dem Maximum, Anker nicht gefunden, Ausschnitt prüfen/)).toBeInTheDocument();
  });

  it("draws a box for the chosen field by dragging on the page", async () => {
    wrap(<OcrLayoutEditor template={template({ field_regions: null })} onSaved={vi.fn()} />);
    const surface = screen.getByTestId("ocr-layout-surface");
    surface.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 400, right: 200, bottom: 400, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.change(screen.getByRole("combobox", { name: "Rechteck zeichnen für" }), { target: { value: "parked" } });
    fireEvent.pointerDown(surface, { clientX: 20, clientY: 40, pointerId: 1 });
    fireEvent.pointerMove(surface, { clientX: 100, clientY: 80, pointerId: 1 });
    fireEvent.pointerUp(surface, { clientX: 120, clientY: 100, pointerId: 1 });
    expect(await screen.findByRole("spinbutton", { name: "Links % für parked" })).toHaveValue(10);
    expect(screen.getByRole("spinbutton", { name: "Breite % für parked" })).toHaveValue(50);
    expect(screen.getByRole("spinbutton", { name: "Höhe % für parked" })).toHaveValue(15);
    // The next field without a box is selected for drawing.
    expect(screen.getByRole("combobox", { name: "Rechteck zeichnen für" })).toHaveValue("cubes");
  });
});

describe("OCR scan retry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.endsWith("/score-sheet-scans")) {
        return Promise.resolve({ data: [
          { id: "s1", template_id: "t", team_id: "t1", file_name: "failed.jpg", status: "failed", extracted_values: null, error: "Template has no configured OCR field regions", created_at: "" },
          { id: "s2", template_id: "t", team_id: "t1", file_name: "busy.jpg", status: "processing", extracted_values: null, error: null, created_at: "" },
        ] });
      }
      if (url === "/v1/events/ev") return Promise.resolve({ data: { id: "ev", season_id: "se" } });
      return Promise.resolve({ data: [] });
    });
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
  });

  function renderScans() {
    return wrap(
      <MemoryRouter initialEntries={["/events/ev/scans"]}>
        <Routes><Route path="/events/:eventId/scans" element={<ScanReviewPage />} /></Routes>
      </MemoryRouter>,
    );
  }

  it("sends a failed scan back to the OCR worker", async () => {
    useAuthStore.setState({ user: { id: "u", is_superuser: false, roles: [], permissions: ["scoring:read", "scoring:write"] } as never });
    renderScans();
    fireEvent.click(await screen.findByRole("button", { name: "failed.jpg erneut verarbeiten" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/v1/events/ev/score-sheet-scans/s1/retry"));
    expect(screen.queryByRole("button", { name: "busy.jpg erneut verarbeiten" })).not.toBeInTheDocument();
  });

  it("offers no retry to read-only users", async () => {
    useAuthStore.setState({ user: { id: "u", is_superuser: false, roles: [], permissions: ["scoring:read"] } as never });
    renderScans();
    expect(await screen.findByText(/failed\.jpg/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /erneut verarbeiten/ })).not.toBeInTheDocument();
  });
});

describe("ScoreSheetsPage", () => {
  it("lists the templates of the current event's season", async () => {
    vi.clearAllMocks();
    (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === "/v1/events/ev") return Promise.resolve({ data: { id: "ev", season_id: "se" } });
      if (url === "/scoring/seasons/se/score-sheets") {
        return Promise.resolve({ data: [{ id: "tpl", label: "Botball 2026", year: 2026, game_theme: null, is_active: true, file_name: "s.pdf", ocr_status: "done", confirmed_fields_count: 3, uploaded_at: "" }] });
      }
      return Promise.resolve({ data: {} });
    });
    wrap(
      <MemoryRouter initialEntries={["/events/ev/scoring/score-sheets"]}>
        <Routes><Route path="/events/:eventId/scoring/score-sheets" element={<ScoreSheetsPage />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Botball 2026")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/scoring/seasons/se/score-sheets", { params: {} });
  });
});
