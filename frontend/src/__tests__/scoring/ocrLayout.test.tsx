import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import OcrLayoutEditor from "@/modules/scoring/score-sheets/components/OcrLayoutEditor";
import { fitRegion, normalizeRegions, rectFromPoints } from "@/modules/scoring/score-sheets/layout";
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
      anchors: [{ name: "corner", x: 0, y: 0, width: 10, height: 10 }],
      field_regions: [
        { key: "cubes", x: 0.1, y: 0.1, width: 0.25, height: 0.05 },
        { key: "parked", x: 0.1, y: 0.1, width: 0.1, height: 0.03 },
      ],
      validation_rules: { strict: true },
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
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
