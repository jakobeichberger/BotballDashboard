import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router";
import SettingsPage from "@/pages/SettingsPage";
import ConfirmHost from "@/components/ConfirmHost";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

function mockApi(overrides: Record<string, any> = {}) {
  const data: Record<string, any> = {
    "/auth/users": [],
    "/auth/roles": [],
    "/seasons": [],
    ...overrides,
  };
  (api.get as any).mockImplementation((url: string) =>
    Promise.resolve({ data: url in data ? data[url] : null })
  );
}

function renderPage(initialPath = "/settings/users") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/settings/*" element={<SettingsPage />} />
        </Routes>
        <ConfirmHost />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: "token",
      user: { id: "admin", email: "admin@example.org", display_name: "Admin", is_superuser: true, preferred_language: "de", theme: "system", roles: [] },
    });
    mockApi();
  });

  it("renders the settings heading and navigation", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /einstellungen/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /benutzer/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /saison-module/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /benutzer anlegen/i })).toBeInTheDocument();
  });

  it("renders the users sub-page with its table heading", () => {
    renderPage("/settings/users");
    expect(screen.getByRole("heading", { name: /^benutzer$/i })).toBeInTheDocument();
    expect(screen.getByText(/e-mail/i)).toBeInTheDocument();
  });

  it("renders the season modules sub-page", async () => {
    renderPage("/settings/modules");
    expect(await screen.findByRole("heading", { name: /saison-module/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /speichern/i })).toBeInTheDocument();
  });

  it("offers the manual printer type instead of an invalid one", async () => {
    renderPage("/settings/printers");
    await userEvent.setup().click(screen.getByRole("button", { name: /drucker hinzufügen/i }));
    const options = screen.getAllByRole("option").map((option) => (option as HTMLOptionElement).value);
    expect(options).toEqual(expect.arrayContaining(["bambu", "octoprint", "generic"]));
    expect(screen.queryByText("Generisch")).not.toBeInTheDocument();
  });

  it("edits a team's print quota for the selected event", async () => {
    const user = userEvent.setup();
    mockApi({
      "/v1/events": [{ id: "e1", season_id: "s1", name: "ECER" }],
      "/printing/events/e1/quotas": [{
        id: "q1", team_id: "t1", team_name: "Team One", season_id: "s1", event_id: "e1",
        max_parts: 4, soft_limit_parts: 3, max_grams: null, used_parts: 1, used_grams: 20,
        open_parts: 2, open_grams: 0, notes: null,
      }],
    });
    (api.put as any).mockResolvedValue({ data: {} });
    renderPage("/settings/printers");
    expect(await screen.findByText("Team One")).toBeInTheDocument();
    expect(screen.getByText(/1 \+ 2 offen/)).toBeInTheDocument();
    const hard = screen.getByLabelText(/hard-limit team one/i);
    await user.clear(hard);
    await user.type(hard, "6");
    await user.type(screen.getByLabelText(/max\. gramm team one/i), "500");
    await user.click(screen.getAllByRole("button", { name: /speichern/i })[0]);
    expect(api.put).toHaveBeenCalledWith("/printing/quotas", {
      team_id: "t1", season_id: "s1", event_id: "e1", max_parts: 6, soft_limit_parts: 3,
      max_grams: 500, clear_max_grams: false,
    });
  });

  it("shows the season lifecycle and offers archive, clone and export", async () => {
    mockApi({
      "/seasons": [
        { id: "s1", name: "Botball 2025", year: 2025, status: "finished", is_active: false },
        { id: "s2", name: "Botball 2024", year: 2024, status: "archived", is_active: false },
      ],
    });
    (api.patch as any).mockResolvedValue({ data: {} });
    (api.post as any).mockResolvedValue({ data: {} });
    renderPage("/settings/seasons");
    expect(await screen.findByText("Abgeschlossen")).toBeInTheDocument();
    expect(screen.getByText("Archiviert")).toBeInTheDocument();
    // Archived seasons cannot be deleted.
    expect(screen.getAllByRole("button", { name: "Löschen" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Archivieren" }));
    // Archiving asks first, in the app's own dialog.
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Botball 2025");
    fireEvent.click(within(dialog).getByRole("button", { name: "Archivieren" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/seasons/s1", { status: "archived" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Klonen" })[0]);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Botball 2026" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Klonen" })[0]);
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/seasons/s1/clone", { name: "Botball 2026", year: 2026 })
    );
  });

  it("edits a role's permissions", async () => {
    mockApi({
      "/auth/roles": [{ id: "r1", name: "helper", description: null, is_system: false, permissions: [{ id: "p1", name: "teams:read" }] }],
      "/auth/permissions": [{ id: "p1", name: "teams:read" }, { id: "p2", name: "teams:write" }],
    });
    (api.put as any).mockResolvedValue({ data: {} });
    renderPage("/settings/roles");
    fireEvent.click(await screen.findByRole("button", { name: /rechte bearbeiten/i }));
    fireEvent.click(await screen.findByRole("button", { name: "teams:write" }));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/auth/roles/r1", { permission_names: ["teams:read", "teams:write"] })
    );
  });
});
