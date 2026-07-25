import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import FormulasPage from "@/pages/FormulasPage";

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    put: (...args: unknown[]) => put(...args),
  },
}));

const EFFECTIVE = [
  { key: "seed_total", expression: "avg_best(seed_runs, 2)" },
  { key: "overall", expression: "seed_total / 100" },
];

const REFERENCE = {
  inputs: { seed_runs: "List of this team's seeding run scores" },
  row_functions: [
    { name: "avg_best", signature: "avg_best(values, k)", description: "Mean of the best k" },
  ],
  scope_functions: [
    { name: "rank", signature: "rank(column)", description: "Rank by column" },
  ],
  defaults: { botball: EFFECTIVE },
};

const PREVIEW = {
  ok: true,
  order: ["seed_total", "overall"],
  issues: [],
  rows: [
    {
      team_id: "t1",
      team_name: "Alpha",
      rank: 1,
      values: { seed_total: 250, overall: 2.5 },
    },
  ],
};

function mockRoutes() {
  get.mockImplementation((url: string) => {
    if (url === "/v1/events/e1")
      return Promise.resolve({ data: { id: "e1", season_id: "s1", name: "ECER 2026" } });
    if (url === "/scoring/formulas/reference") return Promise.resolve({ data: REFERENCE });
    if (url.endsWith("/effective")) return Promise.resolve({ data: EFFECTIVE });
    if (url.endsWith("/bracket-weights")) return Promise.resolve({ data: { A: 1 } });
    return Promise.resolve({ data: [] });
  });
  post.mockResolvedValue({ data: PREVIEW });
  put.mockResolvedValue({ data: [] });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/events/e1/formulas"]}>
        <Routes>
          <Route path="/events/:eventId/formulas" element={<FormulasPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FormulasPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRoutes();
  });

  it("loads the season's effective formula set into the editor", async () => {
    renderPage();
    expect(await screen.findByDisplayValue("seed_total")).toBeInTheDocument();
    expect(screen.getByDisplayValue("avg_best(seed_runs, 2)")).toBeInTheDocument();
  });

  it("shows the available variables and functions", async () => {
    renderPage();
    expect(await screen.findByText("seed_runs")).toBeInTheDocument();
    expect(screen.getByText("avg_best(values, k)")).toBeInTheDocument();
    expect(screen.getByText("rank(column)")).toBeInTheDocument();
  });

  it("previews against real data and renders a column per formula", async () => {
    renderPage();
    await screen.findByDisplayValue("seed_total");
    await waitFor(
      () => expect(screen.getByText("Alpha")).toBeInTheDocument(),
      { timeout: 3000 },
    );
    expect(screen.getByText("2.5")).toBeInTheDocument();
  });

  it("enables saving only once something was edited", async () => {
    renderPage();
    await screen.findByDisplayValue("seed_total");

    const save = screen.getByRole("button", { name: "Speichern" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByDisplayValue("seed_total / 100"), {
      target: { value: "seed_total / 50" },
    });
    expect(save).toBeEnabled();
  });

  it("sends the edited set to the API on save", async () => {
    renderPage();
    await screen.findByDisplayValue("seed_total");

    fireEvent.change(screen.getByDisplayValue("seed_total / 100"), {
      target: { value: "seed_total / 50" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).toHaveBeenCalled());
    const [url, body] = put.mock.calls[0] as [string, { formulas: { expression: string }[] }];
    expect(url).toBe("/scoring/formulas/seasons/s1/botball");
    expect(body.formulas[1].expression).toBe("seed_total / 50");
  });

  it("surfaces a formula error from the preview", async () => {
    post.mockResolvedValue({
      data: {
        ok: false,
        order: [],
        rows: [],
        issues: [{ key: "overall", team_id: null, message: "Syntax error: invalid syntax" }],
      },
    });
    renderPage();
    await screen.findByDisplayValue("seed_total");
    await waitFor(
      () => expect(screen.getByText(/Syntax error/)).toBeInTheDocument(),
      { timeout: 3000 },
    );
  });
});
