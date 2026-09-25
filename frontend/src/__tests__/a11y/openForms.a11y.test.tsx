/**
 * axe on the forms as the user sees them after opening them (create forms,
 * dialogs, the admin printer form) — the page-level tests only cover the
 * closed state. Dialogs render into a portal, so these check document.body.
 */
import "fake-indexeddb/auto";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router";
import { axe, toHaveNoViolations } from "jest-axe";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import SettingsPage from "@/pages/SettingsPage";
import BotsPage from "@/pages/BotsPage";
import PrintingPage from "@/pages/PrintingPage";
import ScoreEntryPage from "@/pages/ScoreEntryPage";
import EventScoringPage from "@/pages/EventScoringPage";

expect.extend(toHaveNoViolations);

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  isQueuedResponse: () => false,
}));

// color-contrast needs a layout engine; the tokens are checked in the browser.
const AXE_OPTS = { rules: { "color-contrast": { enabled: false } } };

const SCHEMA = { fields: [{ key: "cubes", label: "Würfel", multiplier: 3, max_value: null, type: "count" }, { key: "flag", label: "Flagge", multiplier: 50, max_value: 1, type: "boolean" }] };

function mockApi() {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url === "/seasons/active") return Promise.resolve({ data: { id: "s1", name: "2026" } });
    if (url === "/seasons") return Promise.resolve({ data: [{ id: "s1", name: "2026", year: 2026, status: "active", is_active: true }] });
    if (url === "/teams") return Promise.resolve({ data: [{ id: "t1", name: "Alpha" }] });
    if (url === "/auth/roles") return Promise.resolve({ data: [{ id: "r1", name: "juror", description: null, is_system: true, permissions: [] }] });
    if (url.endsWith("/schema") || url.endsWith("/scoring-schema")) return Promise.resolve({ data: SCHEMA });
    if (url.endsWith("/registrations")) return Promise.resolve({ data: [{ id: "r1", team_id: "t1", team_name: "Alpha", team_number: "A-1", seed_number: 1 }] });
    if (url === "/v1/events/ev") return Promise.resolve({ data: { id: "ev", season_id: "s1", name: "Regional" } });
    if (url.endsWith("/rules")) return Promise.resolve({ data: { tiebreakers: [], referee_checklist: [] } });
    return Promise.resolve({ data: [] });
  });
}

function renderAt(path: string, route: string, element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <main>
          <Routes><Route path={route} element={element} /></Routes>
        </main>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("open forms accessibility (axe)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
    useAuthStore.setState({ accessToken: "tok", user: { id: "u1", display_name: "Admin", is_superuser: true, roles: [], permissions: [] } as never });
  });

  it("settings: create-user form", async () => {
    renderAt("/settings/users", "/settings/*", <SettingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Benutzer anlegen" }));
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Rollen" })).toBeInTheDocument();
    expect(await axe(document.body, AXE_OPTS)).toHaveNoViolations();
  });

  it("settings: create-season form", async () => {
    renderAt("/settings/seasons", "/settings/*", <SettingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Saison anlegen" }));
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(await axe(document.body, AXE_OPTS)).toHaveNoViolations();
  });

  it("bots: create form", async () => {
    renderAt("/bots", "/bots", <BotsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Bot anlegen" }));
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(await axe(document.body, AXE_OPTS)).toHaveNoViolations();
  });

  it("printing: new job dialog and printer form", async () => {
    renderAt("/printing", "/printing", <PrintingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Druckauftrag" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await axe(document.body, AXE_OPTS)).toHaveNoViolations();
  });

  it("score entry form", async () => {
    renderAt("/scoring/entry", "/scoring/entry", <ScoreEntryPage />);
    expect(await screen.findByLabelText(/Würfel/)).toBeInTheDocument();
    expect(await axe(document.body, AXE_OPTS)).toHaveNoViolations();
  });

  it("mobile scoring form", async () => {
    renderAt("/events/ev/scoring", "/events/:eventId/scoring", <EventScoringPage />);
    expect(await screen.findByLabelText("Team")).toBeInTheDocument();
    expect(await axe(document.body, AXE_OPTS)).toHaveNoViolations();
  });
});
