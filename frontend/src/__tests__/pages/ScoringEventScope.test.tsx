import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { ReactElement } from "react";
import DEPage from "@/pages/DEPage";
import AerialPage from "@/pages/AerialPage";
import DocScoringPage from "@/pages/DocScoringPage";
import { api } from "@/lib/api";
import { aerialMean, regionalDocScore } from "@/lib/scoring";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), patch: vi.fn() } }));

const SEASON = {
  id: "s1",
  year: 2026,
  use_documentation_scoring: true,
  use_paper_scoring: false,
  active_categories: ["botball"],
};
const TEAMS = [{ id: "t1", name: "Alpha", team_number: "1" }];

function mockApi(extra: Record<string, unknown> = {}) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/v1/events/e2") return Promise.resolve({ data: { id: "e2", season_id: "s1" } });
    if (url === "/seasons/s1") return Promise.resolve({ data: SEASON });
    if (url === "/seasons/active") return Promise.resolve({ data: SEASON });
    if (url === "/teams") return Promise.resolve({ data: TEAMS });
    for (const [key, value] of Object.entries(extra)) {
      if (url.includes(key)) return Promise.resolve({ data: value });
    }
    return Promise.resolve({ data: [] });
  });
  (api.put as any).mockResolvedValue({ data: [] });
}

function renderAt(path: string, element: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/events/e2${path}`]}>
        <Routes>
          <Route path={`/events/:eventId${path}`} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const calledUrls = () => (api.get as any).mock.calls.map((c: unknown[]) => c[0] as string);

describe("scoring pages under /events/:eventId", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("DEPage reads and writes the route's event, not the season default", async () => {
    mockApi();
    renderAt("/scoring/de", <DEPage />);
    await waitFor(() => expect(calledUrls()).toContain("/scoring/events/e2/de-results"));
    expect(calledUrls().some((u: string) => u.startsWith("/scoring/seasons/"))).toBe(false);

    fireEvent.change(await screen.findByLabelText("Bracket für Alpha"), { target: { value: "A" } });
    fireEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect((api.put as any).mock.calls[0][0]).toBe("/scoring/events/e2/de-results");
  });

  it("AerialPage shows the mean of all runs", async () => {
    mockApi({
      "/aerial-results": [{ team_id: "t1", runs: [20, 100, 80, 0] }],
    });
    renderAt("/scoring/aerial", <AerialPage />);
    // (20 + 100 + 80 + 0) / 4 = 50 — not the best-two average of 90.
    expect(await within(await screen.findByRole("table")).findByText("50,0")).toBeInTheDocument();
    expect(calledUrls()).toContain("/scoring/events/e2/aerial-results");
  });

  it("DocScoringPage shows the weighted doc score and the formula value", async () => {
    mockApi({
      "/doc-scores": [{ team_id: "t1", part1: 100, part2: 100, part3: 100, onsite: 0 }],
      "/ranking/overall": [{ team_id: "t1", values: { doc_score: 1 } }],
    });
    renderAt("/scoring/doc", <DocScoringPage />);
    // 0.2 + 0.2 + 0.2 + 0.4 * 0
    expect(await screen.findByText("0,6000")).toBeInTheDocument();
    expect(await screen.findByText("1,0000")).toBeInTheDocument();
    expect(calledUrls()).toContain("/scoring/events/e2/doc-scores");
  });
});

describe("scoring helpers", () => {
  it("weights documentation 0.2/0.2/0.2/0.4 and counts missing parts as 0", () => {
    expect(regionalDocScore([100, 100, 100, 100])).toBeCloseTo(1);
    expect(regionalDocScore([100, 50, null, 50])).toBeCloseTo(0.5);
    expect(regionalDocScore([null, null, null, null])).toBeNull();
  });

  it("averages every aerial run", () => {
    expect(aerialMean([20, 100, 80, 0])).toBe(50);
    expect(aerialMean([80, null])).toBe(80);
    expect(aerialMean([])).toBeNull();
  });
});
