import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import SettingsPage from "@/pages/SettingsPage";
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

  it("shows the season lifecycle and offers archive, clone and export", async () => {
    mockApi({
      "/seasons": [
        { id: "s1", name: "Botball 2025", year: 2025, status: "finished", is_active: false },
        { id: "s2", name: "Botball 2024", year: 2024, status: "archived", is_active: false },
      ],
    });
    (api.patch as any).mockResolvedValue({ data: {} });
    (api.post as any).mockResolvedValue({ data: {} });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage("/settings/seasons");
    expect(await screen.findByText("Abgeschlossen")).toBeInTheDocument();
    expect(screen.getByText("Archiviert")).toBeInTheDocument();
    // Archived seasons cannot be deleted.
    expect(screen.getAllByRole("button", { name: "Löschen" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Archivieren" }));
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
