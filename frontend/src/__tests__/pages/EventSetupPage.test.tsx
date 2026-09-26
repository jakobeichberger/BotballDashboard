import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import EventSetupPage from "@/pages/EventSetupPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

// Event setup before and on the event day (review 2026-09, #5): creating the
// first season and event, module switches, public flags, announcements.
// The editors below the form have their own tests; they are stubbed here.
vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn() } }));
vi.mock("@/components/events/PhaseManager", () => ({ default: () => <div data-testid="phase-manager" /> }));
vi.mock("@/components/events/RegistrationManager", () => ({ default: () => <div data-testid="registration-manager" /> }));
vi.mock("@/components/events/EventBracketWeights", () => ({ default: () => <div data-testid="bracket-weights" /> }));
vi.mock("@/modules/scoring/sheet/SchemaEditor", () => ({ default: () => <div data-testid="schema-editor" /> }));
vi.mock("@/modules/scoring/extras/SeasonRulesEditor", () => ({ default: () => <div data-testid="season-rules" /> }));
vi.mock("@/modules/scoring/extras/QualificationPanel", () => ({ default: () => <div data-testid="qualification" /> }));

const get = api.get as ReturnType<typeof vi.fn>;
const post = api.post as ReturnType<typeof vi.fn>;
const patch = api.patch as ReturnType<typeof vi.fn>;
const put = api.put as ReturnType<typeof vi.fn>;

const SEASONS = [
  { id: "s1", name: "Saison 2026", use_seeding: true, use_double_elimination: true, use_documentation_scoring: false, use_aerial: false },
];
const EVENT = {
  id: "e1", season_id: "s1", name: "ECER 2026", slug: "ecer-2026", timezone: "Europe/Vienna", venue: null,
  status: "published", table_count: 4, active_modules: ["seeding", "double_elimination", "paper"],
  public_scoreboard: true, public_schedule: false, public_results: false, public_announcements: false,
};

function mockApi({ seasons = SEASONS, announcements = [] as unknown[] } = {}) {
  get.mockImplementation((url: string) => {
    if (url === "/seasons") return Promise.resolve({ data: seasons });
    if (url === "/v1/events/e1") return Promise.resolve({ data: EVENT });
    if (url === "/v1/events/e1/modules") {
      return Promise.resolve({ data: { active: EVENT.active_modules, season_flags: { use_seeding: true, use_double_elimination: true, use_documentation_scoring: false, use_aerial: false } } });
    }
    if (url === "/dashboard/announcements") return Promise.resolve({ data: announcements });
    return Promise.resolve({ data: null });
  });
}

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/events/new" element={<EventSetupPage />} />
          <Route path="/events/:eventId/settings" element={<><EventSetupPage /><Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const moduleBox = (name: string) => screen.getByRole("checkbox", { name: new RegExp(`^${name}`) });

describe("EventSetupPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
    useAuthStore.setState({
      accessToken: "tok",
      user: { id: "u1", display_name: "Admin", is_superuser: false, roles: [], permissions: ["events:write"] } as never,
    });
  });

  it("creates the first event with the season's modules and a clean slug", async () => {
    post.mockResolvedValue({ data: { id: "e9" } });
    renderAt("/events/new");
    expect(await screen.findByRole("heading", { name: "Erstes Event einrichten" })).toBeInTheDocument();
    const season = screen.getByRole("combobox", { name: "Saison" });
    await waitFor(() => expect(within(season).getAllByRole("option")).toHaveLength(2));
    fireEvent.change(season, { target: { value: "s1" } });
    // The season runs DE but no documentation/aerial: those start switched off.
    expect(moduleBox("Double Elimination")).toBeChecked();
    expect(moduleBox("Dokumentation")).not.toBeChecked();
    expect(screen.getAllByText(/In der Saison deaktiviert/).length).toBe(2);

    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: "GCER Wien" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Slug" }), { target: { value: "GCER Wien 2026!" } });
    expect(screen.getByRole("textbox", { name: "Slug" })).toHaveValue("gcer-wien-2026");
    fireEvent.click(screen.getByRole("checkbox", { name: "Rangliste" }));
    fireEvent.click(screen.getByRole("button", { name: "Event speichern" }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/v1/events", expect.objectContaining({
      season_id: "s1",
      name: "GCER Wien",
      slug: "gcer-wien-2026",
      active_modules: ["seeding", "double_elimination", "paper", "printing", "bots"],
      public_scoreboard: true,
    })));
    // Continues on the new event's settings page.
    expect(await screen.findByTestId("where")).toHaveTextContent("/events/e9/settings");
  });

  it("creates the first season when there is none", async () => {
    mockApi({ seasons: [] });
    post.mockResolvedValue({ data: { id: "s-new" } });
    renderAt("/events/new");
    const name = await screen.findByPlaceholderText("Saisonname");
    const create = screen.getByRole("button", { name: "Saison anlegen" });
    expect(create).toBeDisabled();
    fireEvent.change(name, { target: { value: "Saison 2027" } });
    fireEvent.click(create);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/seasons", expect.objectContaining({
      name: "Saison 2027",
      is_active: true,
      create_default_event: false,
    })));
    expect(await screen.findByRole("status")).toHaveTextContent("Saison wurde angelegt");
  });

  it("edits an event: modules, public flags and table count", async () => {
    patch.mockResolvedValue({ data: EVENT });
    renderAt("/events/e1/settings");
    expect(await screen.findByDisplayValue("ECER 2026")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Event-Verwaltung" })).toBeInTheDocument();
    // Existing events do not pick a season any more.
    expect(screen.queryByRole("combobox", { name: "Saison" })).not.toBeInTheDocument();
    expect(moduleBox("Double Elimination")).toBeChecked();

    fireEvent.click(moduleBox("Double Elimination"));
    fireEvent.click(moduleBox("3D-Druck"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Zeitplan" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Tische" }), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Event speichern" }));

    await waitFor(() => expect(patch).toHaveBeenCalledWith("/v1/events/e1", expect.objectContaining({
      // Kept in the canonical module order.
      active_modules: ["seeding", "paper", "printing"],
      public_schedule: true,
      public_scoreboard: true,
      table_count: 6,
    })));
    expect(await screen.findByRole("status")).toHaveTextContent("Event gespeichert.");
    // The editors of an existing event are shown below the form.
    expect(screen.getByTestId("phase-manager")).toBeInTheDocument();
    expect(screen.getByTestId("registration-manager")).toBeInTheDocument();
  });

  it("marks a module the season switched off", async () => {
    renderAt("/events/e1/settings");
    await screen.findByDisplayValue("ECER 2026");
    fireEvent.click(moduleBox("Aerial"));
    expect(moduleBox("Aerial")).toBeChecked();
    expect(screen.getByText(/In der Saison deaktiviert – bleibt inaktiv/)).toBeInTheDocument();
  });

  it("shows why saving failed", async () => {
    patch.mockRejectedValue({ response: { status: 409, data: { code: "http_409", message: "Slug already in use" } } });
    renderAt("/events/e1/settings");
    await screen.findByDisplayValue("ECER 2026");
    fireEvent.click(screen.getByRole("button", { name: "Event speichern" }));
    const status = await screen.findByRole("status");
    expect(status).not.toHaveTextContent("Event gespeichert.");
    expect(status).not.toBeEmptyDOMElement();
  });

  it("publishes an announcement for the event", async () => {
    useAuthStore.setState({
      user: { id: "u1", display_name: "Admin", is_superuser: false, roles: [], permissions: ["events:write", "dashboard:write"] } as never,
    });
    mockApi({ announcements: [{ id: "a0", event_id: "e1", title: "Mittagspause", body: "12–13 Uhr" }, { id: "a1", event_id: "other", title: "Fremd", body: "" }] });
    post.mockResolvedValue({ data: { id: "a2" } });
    put.mockResolvedValue({ data: {} });
    renderAt("/events/e1/settings");
    // Only this event's announcements are listed.
    expect(await screen.findByRole("heading", { name: "Mittagspause" })).toBeInTheDocument();
    expect(screen.queryByText("Fremd")).not.toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Titel"), { target: { value: "Finale" } });
    fireEvent.change(screen.getByPlaceholderText("Nachricht"), { target: { value: "Um 16 Uhr an Tisch 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Veröffentlichen" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/dashboard/announcements/a2/publish"));
    expect(post).toHaveBeenCalledWith("/dashboard/announcements", {
      title: "Finale",
      body: "Um 16 Uhr an Tisch 1",
      season_id: "s1",
      event_id: "e1",
      audience: "all",
    });
    await waitFor(() => expect(screen.getByPlaceholderText("Titel")).toHaveValue(""));
  });

  it("hides the announcements without dashboard:write", async () => {
    renderAt("/events/e1/settings");
    await screen.findByDisplayValue("ECER 2026");
    expect(screen.queryByRole("heading", { name: "Öffentliche Ankündigungen" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("bracket-weights")).not.toBeInTheDocument();
  });
});
