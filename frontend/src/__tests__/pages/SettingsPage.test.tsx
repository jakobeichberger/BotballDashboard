import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import SettingsPage from "@/pages/SettingsPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));

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
});
