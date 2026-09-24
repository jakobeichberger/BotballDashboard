import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import SettingsPage from "@/pages/SettingsPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn() } }));

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
});
