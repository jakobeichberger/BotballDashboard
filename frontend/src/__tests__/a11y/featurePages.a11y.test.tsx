import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import { api } from "@/lib/api";

import TeamsPage from "@/pages/TeamsPage";
import PapersPage from "@/pages/PapersPage";
import PrintingPage from "@/pages/PrintingPage";
import ScoreboardPage from "@/pages/ScoreboardPage";
import SettingsPage from "@/pages/SettingsPage";
import DEPage from "@/pages/DEPage";
import AerialPage from "@/pages/AerialPage";
import DocScoringPage from "@/pages/DocScoringPage";

expect.extend(toHaveNoViolations);

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), patch: vi.fn() } }));
vi.mock("@/hooks/useAuth", () => ({
  useCurrentUser: () => ({ data: { id: "u1", roles: [] } }),
}));

// color-contrast cannot be computed in jsdom (no layout engine); disable it.
const AXE_OPTS = { rules: { "color-contrast": { enabled: false } } };

const SEASON = {
  id: "s1",
  year: 2026,
  use_seeding: true,
  use_double_elimination: true,
  use_paper_scoring: true,
  use_documentation_scoring: true,
  use_aerial: true,
  active_categories: ["botball"],
};

const TEAMS = [
  { id: "t1", name: "Alpha", team_number: "1", is_active: true, school: "School A", city: "Wien", country: "AT" },
];

function mockApi() {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/seasons/active") return Promise.resolve({ data: SEASON });
    if (url === "/seasons") return Promise.resolve({ data: [SEASON] });
    if (url === "/teams") return Promise.resolve({ data: TEAMS });
    if (url === "/papers") return Promise.resolve({ data: [] });
    if (url === "/printing/jobs") return Promise.resolve({ data: [] });
    if (url === "/auth/users") return Promise.resolve({ data: [] });
    // ranking / results / scores endpoints
    return Promise.resolve({ data: [] });
  });
}

/** Render inside <main> + Router so top-level content sits in a landmark. */
function a11yRender(ui: React.ReactNode, initialEntries: string[] = ["/"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <main>{ui}</main>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("feature pages accessibility (axe)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
  });

  it("TeamsPage has no a11y violations", async () => {
    const { container } = a11yRender(<TeamsPage />);
    await screen.findByRole("heading", { name: /teams/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("PapersPage has no a11y violations", async () => {
    const { container } = a11yRender(<PapersPage />);
    await screen.findByRole("heading", { name: /paper review/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("PrintingPage has no a11y violations", async () => {
    const { container } = a11yRender(<PrintingPage />);
    await screen.findByRole("heading", { name: /3d-druck/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("ScoreboardPage has no a11y violations", async () => {
    const { container } = a11yRender(<ScoreboardPage />);
    await screen.findByRole("heading", { name: /rangliste/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("SettingsPage (users) has no a11y violations", async () => {
    const { container } = a11yRender(
      <Routes>
        <Route path="/settings/*" element={<SettingsPage />} />
      </Routes>,
      ["/settings/users"]
    );
    await screen.findByRole("heading", { name: /einstellungen/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("SettingsPage (modules) has no a11y violations", async () => {
    const { container } = a11yRender(
      <Routes>
        <Route path="/settings/*" element={<SettingsPage />} />
      </Routes>,
      ["/settings/modules"]
    );
    await screen.findByRole("heading", { name: /saison-module/i });
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("DEPage has no a11y violations", async () => {
    const { container } = a11yRender(<DEPage />);
    await screen.findByText("Alpha");
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("AerialPage has no a11y violations", async () => {
    const { container } = a11yRender(<AerialPage />);
    await screen.findByText("Alpha");
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });

  it("DocScoringPage has no a11y violations", async () => {
    const { container } = a11yRender(<DocScoringPage />);
    await screen.findByText("Alpha");
    expect(await axe(container, AXE_OPTS)).toHaveNoViolations();
  });
});
